from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, permissions, viewsets
from .models import Alert, Incident, IncidentCategory
from .serializers import AlertSerializer, CategorySerializer, IncidentSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IncidentCategory.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class IncidentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = IncidentSerializer
    filterset_fields = ("status", "category")

    def get_queryset(self):
        user = self.request.user
        qs = Incident.objects.select_related("category").prefetch_related("timeline")
        if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
            return qs
        if user.is_authority:
            return qs.filter(assigned_organisation__memberships__user=user, assigned_organisation__memberships__is_active=True).distinct()
        return qs.filter(reporter=user)


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AlertSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return Alert.objects.filter(is_published=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))

