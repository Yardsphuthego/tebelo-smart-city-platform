from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin
from .models import EmergencyContact, User


@admin.register(User)
class TebeloUserAdmin(BaseUserAdmin, ModelAdmin):
    ordering = ("first_name", "last_name")
    list_display = ("phone_number", "email", "first_name", "last_name", "role", "is_verified", "is_active")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("first_name", "last_name", "phone_number", "profile_photo")}),
        ("TEBELO", {"fields": ("role", "is_verified", "location_consent", "nearby_alerts_enabled", "preferred_radius_km")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": (
        "phone_number", "email", "first_name", "last_name", "profile_photo", "password1", "password2",
        "role", "is_staff", "is_verified",
    )}),)
    search_fields = ("phone_number", "email", "first_name", "last_name")

admin.site.register(EmergencyContact)
