import hashlib

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from .models import (
    Alert, AuthorityHandoff, AuthorityNotification, DeliveryCase, DeliveryEvent,
    DutyAssignment, DutyShift, Evidence, Incident, IncidentCategory, IncidentEvent,
    Location, Membership, NeighborhoodWatchGroup, NeighborhoodWatchMembership,
    NotificationPreference, OperationalRecommendation, Organisation, ServiceDeskCase,
    ServiceMessage, ServiceRoutingPolicy,
)


class IncidentEventInline(TabularInline):
    model = IncidentEvent
    extra = 0
    readonly_fields = ("actor", "event_type", "from_status", "to_status", "note", "created_at")


class ServiceMessageInline(TabularInline):
    model = ServiceMessage
    extra = 0
    readonly_fields = ("sender", "body", "created_at")


class DeliveryEventInline(TabularInline):
    model = DeliveryEvent
    extra = 0
    readonly_fields = ("event_type", "actor", "organisation", "note", "metadata", "created_at")


class DutyAssignmentInline(TabularInline):
    model = DutyAssignment
    extra = 1


@admin.register(Incident)
class IncidentAdmin(ModelAdmin):
    list_display = ("reference", "category", "watch_group", "display_status", "display_priority", "assigned_organisation", "created_at")
    list_filter = ("status", "priority", "category__domain", "watch_group", "anonymous", "is_public")
    search_fields = ("reference", "description", "address")
    readonly_fields = ("reference", "created_at", "updated_at", "verified_at", "resolved_at")
    inlines = (IncidentEventInline,)
    list_filter_submit = True
    warn_unsaved_form = True

    @display(description="Status", label={
        "reported": "warning", "triaged": "info", "verified": "info", "assigned": "info",
        "dispatched": "primary", "on_scene": "primary", "resolved": "success",
        "closed": "success", "rejected": "danger",
    })
    def display_status(self, obj):
        return obj.status

    @display(description="Priority", label={"low": "success", "medium": "info", "high": "warning", "critical": "danger"})
    def display_priority(self, obj):
        return obj.priority


@admin.register(Alert)
class AlertAdmin(ModelAdmin):
    list_display = ("title", "severity", "scope", "is_published", "starts_at", "ends_at")
    list_filter = ("is_published", "severity", "category", "scope")


@admin.register(ServiceDeskCase)
class ServiceDeskCaseAdmin(ModelAdmin):
    list_display = ("reference", "desk", "request_type", "status", "resident", "assigned_organisation", "updated_at")
    list_filter = ("desk", "request_type", "status", "access_context", "preferred_language")
    search_fields = ("reference", "subject", "resident__email", "resident__phone_number", "location_description")
    readonly_fields = ("reference", "created_at", "updated_at")
    inlines = (ServiceMessageInline,)


@admin.register(NeighborhoodWatchGroup)
class NeighborhoodWatchGroupAdmin(ModelAdmin):
    list_display = ("reference", "name", "area", "status", "police_organisation", "is_map_visible", "created_at")
    list_filter = ("status", "is_map_visible", "area", "police_organisation")
    search_fields = ("reference", "name", "description", "created_by__phone_number", "created_by__email")
    readonly_fields = ("reference", "created_at", "updated_at")


@admin.register(NeighborhoodWatchMembership)
class NeighborhoodWatchMembershipAdmin(ModelAdmin):
    list_display = ("group", "user", "role", "status", "reviewed_by", "updated_at")
    list_filter = ("role", "status", "group")
    search_fields = ("group__reference", "group__name", "user__phone_number", "user__email")


@admin.register(ServiceRoutingPolicy)
class ServiceRoutingPolicyAdmin(ModelAdmin):
    list_display = ("name", "case_type", "destination_organisation", "acknowledgement_minutes", "assignment_minutes", "resolution_minutes", "precedence", "is_active")
    list_filter = ("case_type", "is_active", "destination_organisation")
    search_fields = ("name", "destination_organisation__name")


@admin.register(DutyShift)
class DutyShiftAdmin(ModelAdmin):
    list_display = ("name", "organisation", "starts_at", "ends_at", "is_active")
    list_filter = ("organisation", "is_active")
    inlines = (DutyAssignmentInline,)


@admin.register(DeliveryCase)
class DeliveryCaseAdmin(ModelAdmin):
    list_display = ("reference", "stage", "organisation", "assigned_to", "acknowledgement_due_at", "resolution_due_at", "escalation_level")
    list_filter = ("stage", "organisation", "last_breach")
    search_fields = ("incident__reference", "service_case__reference", "service_case__subject")
    readonly_fields = ("incident", "service_case", "created_at", "updated_at")
    inlines = (DeliveryEventInline,)


@admin.register(AuthorityHandoff)
class AuthorityHandoffAdmin(ModelAdmin):
    list_display = ("case", "from_organisation", "to_organisation", "status", "requested_by", "created_at")
    list_filter = ("status", "from_organisation", "to_organisation")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OperationalRecommendation)
class OperationalRecommendationAdmin(ModelAdmin):
    list_display = ("title", "category", "priority", "status", "last_generated_at")
    list_filter = ("priority", "status", "category")
    search_fields = ("title", "summary")
    readonly_fields = ("fingerprint", "evidence", "last_generated_at", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not obj.fingerprint:
            identity = f"{obj.category}|{obj.title}".strip().lower().encode()
            obj.fingerprint = f"manual:{hashlib.sha256(identity).hexdigest()}"
        super().save_model(request, obj, form, change)


@admin.register(Organisation)
class OrganisationAdmin(ModelAdmin):
    list_display = ("name", "short_name", "kind", "integration_status", "location", "is_active")
    list_filter = ("kind", "integration_status", "is_active", "location")
    search_fields = ("name", "short_name")
    list_editable = ("integration_status", "is_active")
    save_on_top = True


for model in (Location, Membership, IncidentCategory, Evidence, NotificationPreference,
              ServiceMessage, DutyAssignment, AuthorityNotification, DeliveryEvent):
    admin.site.register(model, ModelAdmin)
