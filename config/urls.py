from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView
from accounts.forms import PhoneAuthenticationForm
from core.views import health
from operations import views as operations_views

urlpatterns = [
    path("health/", health, name="health"),
    path("favicon.ico", RedirectView.as_view(url="/static/favicon.svg", permanent=False)),
    path(
        "admin/delivery-engine/",
        admin.site.admin_view(operations_views.admin_delivery_engine),
        name="admin_delivery_engine",
    ),
    path(
        "admin/delivery-engine/<uuid:pk>/",
        admin.site.admin_view(operations_views.admin_delivery_case_detail),
        name="admin_delivery_case_detail",
    ),
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(
        template_name="accounts/login.html", authentication_form=PhoneAuthenticationForm
    ), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include("accounts.urls")),
    path("api/v1/", include("operations.api_urls")),
    path("", include("operations.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "TEBELO system administration"
admin.site.site_title = "TEBELO Admin"
admin.site.enable_nav_sidebar = False
