from django.conf import settings
from django.db.models import Q
from django.utils import timezone


def platform_context(request):
    ticker_alerts = []
    if request.path in {"/", "/accounts/login/", "/accounts/register/"}:
        from operations.models import Alert

        now = timezone.now()
        ticker_alerts = Alert.objects.filter(
            is_published=True, starts_at__lte=now
        ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))[:3]
    can_manage_watch = False
    if request.user.is_authenticated and request.user.is_authority:
        can_manage_watch = (
            request.user.is_superuser
            or request.user.role in {request.user.Role.COMMAND, request.user.Role.ADMIN}
            or request.user.memberships.filter(
                is_active=True, organisation__is_active=True, organisation__kind="police"
            ).exists()
        )
    return {
        "platform_name": "TEBELO", "emergency_number": "999",
        "map_style_url": settings.MAP_STYLE_URL,
        "ticker_alerts": ticker_alerts,
        "can_manage_watch": can_manage_watch,
    }
