from django.db import connection
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def health(request):
    """Small readiness probe used by the production process supervisor."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
