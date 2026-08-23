from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    Alert,
    AuthorityHandoff,
    Incident,
    IncidentCategory,
    NeighborhoodWatchGroup,
    NeighborhoodWatchMembership,
    ServiceDeskCase,
    Organisation,
)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm",
    "audio/mpeg", "audio/mp4", "audio/wav", "application/pdf",
}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,video/mp4,video/webm,audio/*,application/pdf"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        files = data if isinstance(data, (list, tuple)) else [data]
        cleaned = []
        for item in files:
            file = single_clean(item, initial)
            if not file:
                continue
            if file.size > settings.MAX_EVIDENCE_BYTES:
                raise ValidationError(f"Each file must be smaller than {settings.MAX_EVIDENCE_BYTES // 1048576} MB.")
            if file.content_type not in ALLOWED_CONTENT_TYPES:
                raise ValidationError("One or more files use an unsupported format.")
            cleaned.append(file)
        return cleaned


class IncidentReportForm(forms.ModelForm):
    evidence_files = MultipleFileField(required=False, label="Photos, video, audio or PDF evidence")
    location_permission = forms.BooleanField(required=True, label="I consent to sharing this incident location with responding authorities")

    class Meta:
        model = Incident
        fields = (
            "watch_group", "category", "description", "occurred_at", "address",
            "latitude", "longitude", "anonymous",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Describe what happened. Do not include accusations or unnecessary personal details."}),
            "occurred_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "latitude": forms.HiddenInput(), "longitude": forms.HiddenInput(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = IncidentCategory.objects.filter(is_active=True)
        self.fields["watch_group"].required = False
        self.fields["watch_group"].label = "Neighborhood Watch group (optional)"
        if user and user.is_authenticated:
            self.fields["watch_group"].queryset = NeighborhoodWatchGroup.objects.filter(
                status=NeighborhoodWatchGroup.Status.ACTIVE,
                memberships__user=user,
                memberships__status=NeighborhoodWatchMembership.Status.ACTIVE,
            ).distinct()
        else:
            self.fields["watch_group"].queryset = NeighborhoodWatchGroup.objects.none()

    def clean_occurred_at(self):
        value = self.cleaned_data.get("occurred_at")
        if value and value > timezone.now():
            raise ValidationError("The incident time cannot be in the future.")
        return value


class NeighborhoodWatchGroupForm(forms.ModelForm):
    police_review_acknowledgement = forms.BooleanField(
        label="I understand this group requires police review before it becomes active"
    )

    class Meta:
        model = NeighborhoodWatchGroup
        fields = (
            "name", "area", "description", "centre_latitude", "centre_longitude", "radius_km",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Describe the area, purpose and proposed community activities."}),
            "centre_latitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "-24.628200"}),
            "centre_longitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "25.923100"}),
            "radius_km": forms.NumberInput(attrs={"min": "0.1", "max": "10", "step": "0.1"}),
        }


class AuthorityHandoffForm(forms.ModelForm):
    class Meta:
        model = AuthorityHandoff
        fields = ("to_organisation", "reason")
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 4, "placeholder": "Explain why this authority should take ownership."}),
        }

    def __init__(self, *args, current_organisation=None, **kwargs):
        super().__init__(*args, **kwargs)
        organisations = Organisation.objects.filter(is_active=True)
        if current_organisation:
            organisations = organisations.exclude(pk=current_organisation.pk)
        self.fields["to_organisation"].queryset = organisations


class IncidentUpdateForm(forms.ModelForm):
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), required=True, max_length=1000)

    class Meta:
        model = Incident
        fields = ("status", "priority", "assigned_organisation", "assigned_to", "is_public", "public_summary")


class AlertForm(forms.ModelForm):
    class Meta:
        model = Alert
        exclude = ("published_by", "source_incident")
        widgets = {"summary": forms.Textarea(attrs={"rows": 4}), "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}


class ServiceDeskForm(forms.ModelForm):
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Tell the desk how they can help."}), max_length=2000)
    non_emergency_acknowledgement = forms.BooleanField(
        label="I understand this service is not monitored as an emergency line"
    )

    class Meta:
        model = ServiceDeskCase
        fields = (
            "desk", "request_type", "subject", "access_context",
            "location_description", "preferred_language", "preferred_contact", "incident",
        )
        widgets = {
            "location_description": forms.TextInput(attrs={"placeholder": "Village, ward or nearest landmark (optional)"}),
        }

    def clean(self):
        cleaned = super().clean()
        desk = cleaned.get("desk")
        request_type = cleaned.get("request_type")
        permitted = {
            ServiceDeskCase.Desk.POLICE: {
                ServiceDeskCase.RequestType.POLICE_ASSISTANCE,
                ServiceDeskCase.RequestType.POLICE_FOLLOW_UP,
                ServiceDeskCase.RequestType.CRIME_PREVENTION,
                ServiceDeskCase.RequestType.OTHER,
            },
            ServiceDeskCase.Desk.GOVERNMENT: {
                ServiceDeskCase.RequestType.GOVERNMENT_INFORMATION,
                ServiceDeskCase.RequestType.APPLICATION_GUIDANCE,
                ServiceDeskCase.RequestType.SERVICE_REFERRAL,
                ServiceDeskCase.RequestType.OTHER,
            },
            ServiceDeskCase.Desk.TRAFFIC: {
                ServiceDeskCase.RequestType.TRAFFIC_ASSISTANCE,
                ServiceDeskCase.RequestType.OTHER,
            },
            ServiceDeskCase.Desk.FIRE: {
                ServiceDeskCase.RequestType.FIRE_SAFETY,
                ServiceDeskCase.RequestType.OTHER,
            },
        }
        if desk and request_type and request_type not in permitted.get(desk, set()):
            self.add_error("request_type", "Choose a request type that belongs to the selected service.")
        return cleaned
