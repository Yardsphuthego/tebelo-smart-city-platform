import re

from django.core.exceptions import ValidationError


def normalize_phone_number(value):
    """Return a Botswana phone number in a consistent E.164-style format."""
    if value in (None, ""):
        return None

    digits = re.sub(r"\D", "", str(value).strip())
    if digits.startswith("00267"):
        digits = digits[2:]
    elif len(digits) == 8:
        digits = f"267{digits}"

    if len(digits) != 11 or not digits.startswith("267"):
        raise ValidationError(
            "Enter an 8-digit Botswana phone number, for example 71 234 567."
        )
    return f"+{digits}"


def validate_phone_number(value):
    normalize_phone_number(value)
