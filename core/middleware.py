import contextvars
from django.conf import settings

current_request = contextvars.ContextVar("current_request", default=None)


class AuditRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = current_request.set(request)
        try:
            response = self.get_response(request)
            response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
            script_sources = "'self' 'unsafe-inline' https://unpkg.com"
            if request.path.startswith("/admin/"):
                # Unfold's Alpine-powered command palette and shortcut modal compile
                # expressions at runtime. Scope unsafe-eval to the staff-only console.
                script_sources += " 'unsafe-eval'"
            response.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
                f"font-src 'self' https://fonts.gstatic.com; script-src {script_sources}; "
                f"connect-src 'self' {settings.MAP_STYLE_ORIGIN}; worker-src blob:; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
            return response
        finally:
            current_request.reset(token)
