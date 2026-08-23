import uuid
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from core.models import TimeStampedModel
from .phone import normalize_phone_number, validate_phone_number


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra_fields):
        phone_number = extra_fields.get("phone_number")
        if not email and not phone_number:
            raise ValueError("An email address or phone number is required")
        email = self.normalize_email(email) if email else None
        if phone_number:
            extra_fields["phone_number"] = normalize_phone_number(phone_number)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_verified", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        RESIDENT = "resident", "Resident"
        OFFICER = "officer", "Authority officer"
        COMMAND = "command", "Command centre"
        ADMIN = "admin", "System administrator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(
        max_length=16,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_phone_number],
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT, db_index=True)
    is_verified = models.BooleanField(default=False)
    location_consent = models.BooleanField(default=False)
    nearby_alerts_enabled = models.BooleanField(default=True)
    preferred_radius_km = models.PositiveSmallIntegerField(default=3)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    @property
    def is_authority(self):
        return self.is_staff or self.role in {self.Role.OFFICER, self.Role.COMMAND, self.Role.ADMIN}

    def __str__(self):
        name = self.get_full_name().strip()
        return name or self.phone_number or self.email or str(self.pk)


class EmergencyContact(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="emergency_contacts")
    name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=24)
    relationship = models.CharField(max_length=80, blank=True)
