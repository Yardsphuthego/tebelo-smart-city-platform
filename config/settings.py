import os
from pathlib import Path
from urllib.parse import urlparse
from django.templatetags.static import static
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [x.strip() for x in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]

INSTALLED_APPS = [
    "unfold", "unfold.contrib.filters", "unfold.contrib.forms", "unfold.contrib.inlines",
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "django_filters", "core", "accounts", "operations",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.AuditRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages", "core.context_processors.platform_context",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

database_url = os.getenv("DATABASE_URL")
if database_url:
    parsed = urlparse(database_url)
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username, "PASSWORD": parsed.password, "HOST": parsed.hostname,
        "PORT": parsed.port or 5432, "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": os.getenv("DATABASE_SSLMODE", "prefer")},
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.PhoneOrEmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Gaborone"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0" if DEBUG else "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_EVIDENCE_BYTES = int(os.getenv("MAX_EVIDENCE_BYTES", str(25 * 1024 * 1024)))
MAP_STYLE_URL = os.getenv("MAP_STYLE_URL", "https://tiles.openfreemap.org/styles/positron")
_map_style_parts = urlparse(MAP_STYLE_URL)
MAP_STYLE_ORIGIN = f"{_map_style_parts.scheme}://{_map_style_parts.netloc}"
EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "TEBELO <no-reply@localhost>")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle", "rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "120/min", "anon": "20/min"},
}

UNFOLD = {
    "SITE_TITLE": "TEBELO Command",
    "SITE_HEADER": "TEBELO",
    "SITE_SUBHEADER": "City operations platform",
    "SITE_SYMBOL": "shield",
    "SITE_URL": "/",
    "SITE_DROPDOWN": [
        {"icon": "home", "title": "Citizen platform", "link": "/"},
        {"icon": "map", "title": "Public city map", "link": "/map/"},
        {"icon": "monitoring", "title": "Authority workspace", "link": "/command/"},
    ],
    "DASHBOARD_CALLBACK": "operations.admin_dashboard.dashboard_callback",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "BORDER_RADIUS": "10px",
    "STYLES": [lambda request: static("css/admin.css")],
    "SCRIPTS": [lambda request: static("js/loading.js")],
    "COLORS": {
        "primary": {
            "50": "oklch(97.3% .014 178)", "100": "oklch(94.4% .032 177)",
            "200": "oklch(88.7% .061 175)", "300": "oklch(80.2% .105 173)",
            "400": "oklch(68.7% .13 171)", "500": "oklch(57.4% .125 169)",
            "600": "oklch(48.2% .105 169)", "700": "oklch(40.4% .087 170)",
            "800": "oklch(34.2% .069 171)", "900": "oklch(29.8% .056 173)",
            "950": "oklch(19.6% .039 173)",
        }
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {"title": "Command", "separator": True, "items": [
                {"title": "Command overview", "icon": "space_dashboard", "link": reverse_lazy("admin:index")},
                {"title": "Service delivery", "icon": "acute", "link": reverse_lazy("admin_delivery_engine")},
                {"title": "Incidents", "icon": "emergency", "link": reverse_lazy("admin:operations_incident_changelist")},
                {"title": "Virtual services", "icon": "support_agent", "link": reverse_lazy("admin:operations_servicedeskcase_changelist")},
                {"title": "Neighborhood Watch", "icon": "groups", "link": reverse_lazy("admin:operations_neighborhoodwatchgroup_changelist")},
                {"title": "Public alerts", "icon": "notifications_active", "link": reverse_lazy("admin:operations_alert_changelist")},
            ]},
            {"title": "Service network", "separator": True, "collapsible": True, "items": [
                {"title": "Organisations", "icon": "account_balance", "link": reverse_lazy("admin:operations_organisation_changelist")},
                {"title": "Routing policies", "icon": "route", "link": reverse_lazy("admin:operations_serviceroutingpolicy_changelist")},
                {"title": "Duty shifts", "icon": "schedule", "link": reverse_lazy("admin:operations_dutyshift_changelist")},
                {"title": "Locations", "icon": "location_city", "link": reverse_lazy("admin:operations_location_changelist")},
                {"title": "Incident categories", "icon": "category", "link": reverse_lazy("admin:operations_incidentcategory_changelist")},
            ]},
            {"title": "People & access", "separator": True, "collapsible": True, "items": [
                {"title": "User accounts", "icon": "group", "link": reverse_lazy("admin:accounts_user_changelist")},
                {"title": "Memberships", "icon": "badge", "link": reverse_lazy("admin:operations_membership_changelist")},
                {"title": "Watch memberships", "icon": "group_add", "link": reverse_lazy("admin:operations_neighborhoodwatchmembership_changelist")},
            ]},
            {"title": "Governance", "separator": True, "collapsible": True, "items": [
                {"title": "Recommendations", "icon": "recommend", "link": reverse_lazy("admin:operations_operationalrecommendation_changelist")},
                {"title": "Audit trail", "icon": "policy", "link": reverse_lazy("admin:core_auditevent_changelist")},
            ]},
        ],
    },
}
