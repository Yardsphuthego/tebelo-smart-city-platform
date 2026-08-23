import uuid
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel


class Location(TimeStampedModel):
    class Kind(models.TextChoices):
        COUNTRY = "country", "Country"
        DISTRICT = "district", "District"
        CITY = "city", "Town / city"
        WARD = "ward", "Ward"
        AREA = "area", "Area"

    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=20)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    centre_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    centre_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("parent", "code")
        ordering = ("name",)

    def __str__(self):
        return self.name


class Organisation(TimeStampedModel):
    class Kind(models.TextChoices):
        GOVERNMENT = "government", "Government service centre"
        POLICE = "police", "Police"
        TRAFFIC = "traffic", "Traffic police"
        FIRE = "fire", "Fire and rescue"
        MEDICAL = "medical", "Emergency medical services"
        COUNCIL = "council", "City council"
        WATER = "water", "Water authority"
        ELECTRICITY = "electricity", "Electricity authority"
        ROADS = "roads", "Roads authority"
        DISASTER = "disaster", "Disaster management"

    class IntegrationStatus(models.TextChoices):
        CONFIGURED = "configured", "Configured internally"
        ONBOARDING = "onboarding", "Authority onboarding"
        CONNECTED = "connected", "Authority connected"
        SUSPENDED = "suspended", "Integration suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=180)
    short_name = models.CharField(max_length=40, unique=True)
    kind = models.CharField(max_length=24, choices=Kind.choices, db_index=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="organisations")
    emergency_phone = models.CharField(max_length=24, blank=True)
    integration_status = models.CharField(
        max_length=16,
        choices=IntegrationStatus.choices,
        default=IntegrationStatus.CONFIGURED,
        db_index=True,
    )
    source_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
    class Role(models.TextChoices):
        RESPONDER = "responder", "Responder"
        DISPATCHER = "dispatcher", "Dispatcher"
        SUPERVISOR = "supervisor", "Supervisor"
        ANALYST = "analyst", "Analyst"
        ADMIN = "admin", "Organisation administrator"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "organisation")


class IncidentCategory(TimeStampedModel):
    class Domain(models.TextChoices):
        SAFETY = "safety", "Crime and safety"
        TRAFFIC = "traffic", "Traffic"
        FIRE = "fire", "Fire"
        MEDICAL = "medical", "Medical"
        UTILITIES = "utilities", "Utilities"
        INFRASTRUCTURE = "infrastructure", "Infrastructure"
        ENVIRONMENT = "environment", "Weather and environment"
        COMMUNITY = "community", "Community"

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    domain = models.CharField(max_length=24, choices=Domain.choices, db_index=True)
    description = models.CharField(max_length=240, blank=True)
    default_priority = models.CharField(max_length=12, default="medium", choices=(("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")))
    routes_to = models.CharField(max_length=24, choices=Organisation.Kind.choices)
    public_by_default = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("domain", "name")

    def __str__(self):
        return self.name


class NeighborhoodWatchGroup(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending police review"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=32, unique=True, editable=False)
    name = models.CharField(max_length=140)
    area = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="watch_groups")
    description = models.TextField(max_length=1000)
    centre_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    centre_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    radius_km = models.DecimalField(
        max_digits=4, decimal_places=1, default=1,
        validators=[MinValueValidator(0.1), MaxValueValidator(10)],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_watch_groups"
    )
    police_organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.PROTECT,
        related_name="watch_groups", limit_choices_to={"kind": Organisation.Kind.POLICE},
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_map_visible = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=("status", "is_map_visible"))]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"NW-{timezone.now().year}-{self.id.hex[:8].upper()}"
        if self.status != self.Status.ACTIVE:
            self.is_map_visible = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} · {self.name}"


class NeighborhoodWatchMembership(TimeStampedModel):
    class Role(models.TextChoices):
        COORDINATOR = "coordinator", "Coordinator"
        MEMBER = "member", "Member"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        DECLINED = "declined", "Declined"
        LEFT = "left", "Left group"

    group = models.ForeignKey(NeighborhoodWatchGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="watch_memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_watch_memberships",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("group", "user"), name="unique_watch_member")]
        ordering = ("status", "created_at")

    def __str__(self):
        return f"{self.group.name} · {self.user}"


class Incident(TimeStampedModel):
    class Status(models.TextChoices):
        REPORTED = "reported", "Reported"
        TRIAGED = "triaged", "Triaged"
        VERIFIED = "verified", "Verified"
        ASSIGNED = "assigned", "Assigned"
        DISPATCHED = "dispatched", "Response dispatched"
        ON_SCENE = "on_scene", "Responder on scene"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=32, unique=True, editable=False)
    category = models.ForeignKey(IncidentCategory, on_delete=models.PROTECT, related_name="incidents")
    description = models.TextField(max_length=3000)
    public_summary = models.CharField(max_length=300, blank=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reported_incidents")
    anonymous = models.BooleanField(default=False)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    address = models.CharField(max_length=240, blank=True)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name="incidents")
    occurred_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REPORTED, db_index=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    assigned_organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.PROTECT, related_name="incidents")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_incidents")
    is_public = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="duplicate_reports")
    watch_group = models.ForeignKey(
        NeighborhoodWatchGroup, null=True, blank=True, on_delete=models.PROTECT,
        related_name="incidents",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "priority", "-created_at")),
            models.Index(fields=("latitude", "longitude")),
            models.Index(fields=("assigned_organisation", "status")),
        ]

    def save(self, *args, **kwargs):
        if not self.reference:
            prefix = (self.location.code if self.location else "BW").upper()[:4]
            self.reference = f"{prefix}-{timezone.now().year}-{self.id.hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.reference

    @property
    def reporter_display(self):
        if self.anonymous or not self.reporter:
            return "Anonymous resident"
        return self.reporter.get_full_name() or self.reporter.email


def evidence_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"private/evidence/{instance.incident_id}/{uuid.uuid4().hex}{suffix}"


class Evidence(TimeStampedModel):
    class Kind(models.TextChoices):
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"
        AUDIO = "audio", "Audio"
        DOCUMENT = "document", "Document"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="evidence")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    file = models.FileField(upload_to=evidence_path)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, blank=True)


class IncidentEvent(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="timeline")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=40)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class Alert(TimeStampedModel):
    class Scope(models.TextChoices):
        RADIUS = "radius", "Radius"
        LOCATION = "location", "Location"
        CITY = "city", "City-wide"
        NATIONAL = "national", "National"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    summary = models.TextField(max_length=1000)
    category = models.CharField(max_length=24, choices=IncidentCategory.Domain.choices, db_index=True)
    severity = models.CharField(max_length=12, choices=Incident.Priority.choices)
    scope = models.CharField(max_length=12, choices=Scope.choices)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.PROTECT, related_name="alerts")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    source_incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("-starts_at",)

    @property
    def active(self):
        now = timezone.now()
        return self.is_published and self.starts_at <= now and (not self.ends_at or self.ends_at > now)


class NotificationPreference(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    emergency = models.BooleanField(default=True)
    safety = models.BooleanField(default=True)
    traffic = models.BooleanField(default=True)
    fire = models.BooleanField(default=True)
    utilities = models.BooleanField(default=True)
    environment = models.BooleanField(default=True)
    community = models.BooleanField(default=False)


class ServiceDeskCase(TimeStampedModel):
    class Desk(models.TextChoices):
        POLICE = "police", "Virtual Police Station"
        GOVERNMENT = "government", "Government Virtual Assistance"
        TRAFFIC = "traffic", "Traffic Police"
        FIRE = "fire", "Fire and emergency"

    class RequestType(models.TextChoices):
        POLICE_ASSISTANCE = "police_assistance", "Police: non-emergency assistance"
        POLICE_FOLLOW_UP = "police_follow_up", "Police: case or report follow-up"
        CRIME_PREVENTION = "crime_prevention", "Police: crime-prevention guidance"
        GOVERNMENT_INFORMATION = "government_information", "Government: service information"
        APPLICATION_GUIDANCE = "application_guidance", "Government: application guidance"
        SERVICE_REFERRAL = "service_referral", "Government: service referral"
        TRAFFIC_ASSISTANCE = "traffic_assistance", "Traffic: non-emergency assistance"
        FIRE_SAFETY = "fire_safety", "Fire: safety guidance"
        OTHER = "other", "Other assistance"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        ROUTED = "routed", "Routed"
        IN_PROGRESS = "in_progress", "In progress"
        WAITING_RESIDENT = "waiting_resident", "Waiting for resident"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class AccessContext(models.TextChoices):
        REMOTE = "remote", "No nearby office or police station"
        MOBILITY = "mobility", "Mobility or accessibility barrier"
        DIGITAL = "digital", "Prefer digital access"
        OTHER = "other", "Other"

    class Language(models.TextChoices):
        ENGLISH = "en", "English"
        SETSWANA = "tn", "Setswana"

    class ContactMethod(models.TextChoices):
        SECURE_MESSAGE = "message", "Secure TEBELO message"
        PHONE = "phone", "Phone callback"
        SMS = "sms", "SMS update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=32, unique=True, editable=False)
    resident = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_cases")
    desk = models.CharField(max_length=20, choices=Desk.choices)
    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    subject = models.CharField(max_length=160)
    access_context = models.CharField(max_length=20, choices=AccessContext.choices, default=AccessContext.DIGITAL)
    location_description = models.CharField(max_length=240, blank=True)
    preferred_language = models.CharField(max_length=8, choices=Language.choices, default=Language.ENGLISH)
    preferred_contact = models.CharField(max_length=16, choices=ContactMethod.choices, default=ContactMethod.SECURE_MESSAGE)
    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.SET_NULL, related_name="service_cases")
    assigned_organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.PROTECT, related_name="service_cases")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="desk_assignments")
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=("desk", "status", "-created_at"))]

    def save(self, *args, **kwargs):
        if not self.reference:
            prefix = {
                self.Desk.POLICE: "VP",
                self.Desk.GOVERNMENT: "GV",
                self.Desk.TRAFFIC: "TP",
                self.Desk.FIRE: "FE",
            }.get(self.desk, "VS")
            self.reference = f"{prefix}-{timezone.now().year}-{self.id.hex[:8].upper()}"
        if self.status == self.Status.CLOSED:
            self.is_closed = True
        elif self.is_closed:
            self.status = self.Status.CLOSED
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} · {self.subject}"


class ServiceMessage(models.Model):
    case = models.ForeignKey(ServiceDeskCase, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class ServiceRoutingPolicy(TimeStampedModel):
    class CaseType(models.TextChoices):
        INCIDENT = "incident", "Incident report"
        VIRTUAL_SERVICE = "virtual_service", "Virtual-service case"

    name = models.CharField(max_length=140)
    case_type = models.CharField(max_length=20, choices=CaseType.choices, db_index=True)
    incident_category = models.ForeignKey(
        IncidentCategory, null=True, blank=True, on_delete=models.CASCADE,
        related_name="delivery_policies",
    )
    incident_priority = models.CharField(
        max_length=12, choices=Incident.Priority.choices, blank=True,
        help_text="Leave blank to match every priority.",
    )
    service_desk = models.CharField(
        max_length=20, choices=ServiceDeskCase.Desk.choices, blank=True,
    )
    service_request_type = models.CharField(
        max_length=32, choices=ServiceDeskCase.RequestType.choices, blank=True,
    )
    destination_organisation = models.ForeignKey(
        Organisation, on_delete=models.PROTECT, related_name="delivery_policies",
    )
    escalation_organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.PROTECT,
        related_name="escalation_policies",
    )
    acknowledgement_minutes = models.PositiveIntegerField(default=15)
    assignment_minutes = models.PositiveIntegerField(default=30)
    resolution_minutes = models.PositiveIntegerField(default=1440)
    repeat_escalation_minutes = models.PositiveIntegerField(default=30)
    precedence = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("precedence", "name")

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if not (
            self.acknowledgement_minutes <= self.assignment_minutes <= self.resolution_minutes
        ):
            errors["acknowledgement_minutes"] = "Deadlines must increase from acknowledgement to assignment to resolution."
        if self.case_type == self.CaseType.INCIDENT and (self.service_desk or self.service_request_type):
            errors["case_type"] = "Incident policies cannot contain virtual-service matching fields."
        if self.case_type == self.CaseType.VIRTUAL_SERVICE and (self.incident_category_id or self.incident_priority):
            errors["case_type"] = "Virtual-service policies cannot contain incident matching fields."
        if errors:
            raise ValidationError(errors)


class DutyShift(TimeStampedModel):
    organisation = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="duty_shifts")
    name = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ("starts_at",)
        indexes = [models.Index(fields=("organisation", "is_active", "starts_at", "ends_at"))]

    def __str__(self):
        return f"{self.organisation.short_name} · {self.name}"

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "A duty shift must end after it starts."})


class DutyAssignment(TimeStampedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary responder"
        BACKUP = "backup", "Backup responder"
        SUPERVISOR = "supervisor", "Shift supervisor"

    shift = models.ForeignKey(DutyShift, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="duty_assignments")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)
    is_available = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("shift", "user"), name="unique_shift_assignment")]

    def __str__(self):
        return f"{self.shift} · {self.user}"

    def clean(self):
        if self.shift_id and self.user_id and not Membership.objects.filter(
            organisation=self.shift.organisation, user=self.user, is_active=True
        ).exists():
            raise ValidationError({"user": "This user is not an active member of the shift organisation."})


class DeliveryCase(TimeStampedModel):
    class Stage(models.TextChoices):
        OPEN = "open", "Awaiting acknowledgement"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.OneToOneField(
        Incident, null=True, blank=True, on_delete=models.CASCADE, related_name="delivery_case"
    )
    service_case = models.OneToOneField(
        ServiceDeskCase, null=True, blank=True, on_delete=models.CASCADE, related_name="delivery_case"
    )
    policy = models.ForeignKey(
        ServiceRoutingPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="delivery_cases"
    )
    organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.PROTECT, related_name="delivery_cases"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="delivery_assignments",
    )
    escalated_to = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.PROTECT,
        related_name="escalated_delivery_cases",
    )
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.OPEN, db_index=True)
    acknowledgement_due_at = models.DateTimeField(db_index=True)
    assignment_due_at = models.DateTimeField(db_index=True)
    resolution_due_at = models.DateTimeField(db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    escalation_level = models.PositiveSmallIntegerField(default=0)
    last_escalated_at = models.DateTimeField(null=True, blank=True)
    last_breach = models.CharField(max_length=24, blank=True)

    class Meta:
        ordering = ("acknowledgement_due_at", "created_at")
        constraints = [models.CheckConstraint(
            condition=(
                models.Q(incident__isnull=False, service_case__isnull=True)
                | models.Q(incident__isnull=True, service_case__isnull=False)
            ),
            name="delivery_case_has_one_source",
        )]
        indexes = [models.Index(fields=("stage", "organisation", "acknowledgement_due_at"))]

    @property
    def source(self):
        return self.incident or self.service_case

    @property
    def reference(self):
        return self.source.reference

    @property
    def subject(self):
        if self.incident_id:
            return str(self.incident.category)
        return self.service_case.subject

    def __str__(self):
        return f"{self.reference} · {self.get_stage_display()}"


class DeliveryEvent(models.Model):
    case = models.ForeignKey(DeliveryCase, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    organisation = models.ForeignKey(Organisation, null=True, blank=True, on_delete=models.SET_NULL)
    event_type = models.CharField(max_length=40, db_index=True)
    note = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("created_at",)


class AuthorityHandoff(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Awaiting acceptance"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        CANCELLED = "cancelled", "Cancelled"

    case = models.ForeignKey(DeliveryCase, on_delete=models.CASCADE, related_name="handoffs")
    from_organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.PROTECT, related_name="outgoing_handoffs"
    )
    to_organisation = models.ForeignKey(
        Organisation, on_delete=models.PROTECT, related_name="incoming_handoffs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_handoffs"
    )
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="responded_handoffs",
    )
    reason = models.TextField(max_length=1000)
    response_note = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class AuthorityNotification(TimeStampedModel):
    class Kind(models.TextChoices):
        ASSIGNMENT = "assignment", "Assignment"
        SLA_BREACH = "sla_breach", "SLA breach"
        HANDOFF = "handoff", "Authority handoff"
        RECOMMENDATION = "recommendation", "Recommendation"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="authority_notifications")
    delivery_case = models.ForeignKey(
        DeliveryCase, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=180)
    body = models.CharField(max_length=500)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("user", "read_at", "-created_at"))]


class OperationalRecommendation(TimeStampedModel):
    class Priority(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        IMPLEMENTED = "implemented", "Implemented"
        DISMISSED = "dismissed", "Dismissed"

    fingerprint = models.CharField(max_length=160, unique=True)
    category = models.CharField(max_length=40, db_index=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.MEDIUM)
    title = models.CharField(max_length=180)
    summary = models.TextField(max_length=1200)
    evidence = models.JSONField(default=dict, blank=True)
    source_label = models.CharField(max_length=160, blank=True)
    source_url = models.URLField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED, db_index=True)
    last_generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("priority", "-last_generated_at")

    def __str__(self):
        return self.title
