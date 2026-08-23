from rest_framework.routers import DefaultRouter
from .api import AlertViewSet, CategoryViewSet, IncidentViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("incidents", IncidentViewSet, basename="incident")
router.register("alerts", AlertViewSet, basename="alert")
urlpatterns = router.urls

