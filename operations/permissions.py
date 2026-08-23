from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied


def can_manage_incident(user, incident):
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        return True
    return user.is_authority and user.memberships.filter(organisation=incident.assigned_organisation, is_active=True).exists()


class AuthorityRequiredMixin(AccessMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_authority:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
