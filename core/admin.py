from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__email")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
