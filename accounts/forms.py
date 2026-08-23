from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import User
from .phone import normalize_phone_number


class PhoneAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Phone number or authority email",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autofocus": True,
                "placeholder": "71 234 567",
            }
        ),
    )


class RegisterForm(UserCreationForm):
    phone_number = forms.CharField(
        label="Botswana phone number",
        help_text="Use your 8-digit number. We store it as +267 for secure sign-in.",
        widget=forms.TextInput(
            attrs={"autocomplete": "tel", "inputmode": "tel", "placeholder": "71 234 567"}
        ),
    )
    consent = forms.BooleanField(label="I accept the privacy notice and terms of service")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone_number", "password1", "password2")

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("An account already uses this phone number.")
        return phone_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = None
        user.role = User.Role.RESIDENT
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.is_superuser:
            self.fields.pop("profile_photo", None)

    class Meta:
        model = User
        fields = ("profile_photo", "first_name", "last_name", "phone_number", "location_consent", "nearby_alerts_enabled", "preferred_radius_km")

    def clean_phone_number(self):
        return normalize_phone_number(self.cleaned_data["phone_number"])
