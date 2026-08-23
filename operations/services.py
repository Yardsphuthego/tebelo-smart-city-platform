import hashlib
import math
from django.db import transaction
from django.utils import timezone
from core.models import audit
from .models import Evidence, Incident, IncidentEvent, Organisation

TRANSITIONS = {
    Incident.Status.REPORTED: {Incident.Status.TRIAGED, Incident.Status.REJECTED},
    Incident.Status.TRIAGED: {Incident.Status.VERIFIED, Incident.Status.REJECTED},
    Incident.Status.VERIFIED: {Incident.Status.ASSIGNED},
    Incident.Status.ASSIGNED: {Incident.Status.DISPATCHED},
    Incident.Status.DISPATCHED: {Incident.Status.ON_SCENE},
    Incident.Status.ON_SCENE: {Incident.Status.RESOLVED},
    Incident.Status.RESOLVED: {Incident.Status.CLOSED, Incident.Status.ON_SCENE},
    Incident.Status.CLOSED: set(), Incident.Status.REJECTED: set(),
}


def classify_evidence(content_type):
    if content_type.startswith("image/"):
        return Evidence.Kind.PHOTO
    if content_type.startswith("video/"):
        return Evidence.Kind.VIDEO
    if content_type.startswith("audio/"):
        return Evidence.Kind.AUDIO
    return Evidence.Kind.DOCUMENT


def create_incident(*, form, user, request):
    with transaction.atomic():
        incident = form.save(commit=False)
        incident.reporter = user
        incident.priority = incident.category.default_priority
        incident.is_public = False
        if incident.watch_group_id:
            incident.assigned_organisation = (
                incident.watch_group.police_organisation
                or Organisation.objects.filter(
                    kind=Organisation.Kind.POLICE, is_active=True,
                ).order_by("created_at").first()
            )
        else:
            incident.assigned_organisation = Organisation.objects.filter(
                kind=incident.category.routes_to, is_active=True,
            ).order_by("created_at").first()
        incident.save()
        IncidentEvent.objects.create(incident=incident, actor=user, event_type="reported", to_status=incident.status)
        if incident.assigned_organisation:
            IncidentEvent.objects.create(incident=incident, event_type="routed", note=f"Routed to {incident.assigned_organisation.name}")
        for upload in form.cleaned_data.get("evidence_files", []):
            digest = hashlib.sha256()
            for chunk in upload.chunks():
                digest.update(chunk)
            upload.seek(0)
            Evidence.objects.create(
                incident=incident, uploaded_by=user, file=upload, kind=classify_evidence(upload.content_type),
                original_name=upload.name[:255], content_type=upload.content_type, size=upload.size, sha256=digest.hexdigest(),
            )
        audit(request=request, action="incident.created", obj=incident, metadata={
            "reference": incident.reference,
            "anonymous": incident.anonymous,
            "watch_group": incident.watch_group.reference if incident.watch_group_id else "",
        })
        return incident


def update_incident(*, incident, form, user, request):
    old_status = incident.status
    updated = form.save(commit=False)
    if updated.status != old_status and updated.status not in TRANSITIONS.get(old_status, set()):
        form.add_error("status", f"Cannot move directly from {incident.get_status_display()} to {updated.get_status_display()}.")
        return None
    if updated.status == Incident.Status.VERIFIED and not updated.verified_at:
        updated.verified_at = timezone.now()
    if updated.status == Incident.Status.RESOLVED and not updated.resolved_at:
        updated.resolved_at = timezone.now()
    updated.save()
    form.save_m2m()
    IncidentEvent.objects.create(
        incident=updated, actor=user, event_type="status_changed" if old_status != updated.status else "updated",
        from_status=old_status, to_status=updated.status, note=form.cleaned_data["note"],
    )
    audit(request=request, action="incident.updated", obj=updated, metadata={"from": old_status, "to": updated.status})
    return updated


def distance_km(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
