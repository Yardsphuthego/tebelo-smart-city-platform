from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import ValidationError

from .phone import normalize_phone_number


class PhoneOrEmailBackend(ModelBackend):
    """Authenticate residents by phone while retaining authority email access."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email")
        if not identifier or password is None:
            return None

        user_model = get_user_model()
        try:
            if "@" in identifier:
                user = user_model.objects.get(email__iexact=identifier.strip())
            else:
                user = user_model.objects.get(
                    phone_number=normalize_phone_number(identifier)
                )
        except (user_model.DoesNotExist, ValidationError):
            user_model().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
