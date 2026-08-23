from django.db import transaction
from rest_framework import serializers
from core.models import audit
from .models import Alert, Incident, IncidentCategory, IncidentEvent, Organisation


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentCategory
        fields = ("id", "name", "slug", "domain", "description")


class IncidentEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = IncidentEvent
        fields = ("event_type", "from_status", "to_status", "note", "created_at", "actor_name")

    def get_actor_name(self, obj):
        return obj.actor.get_full_name() if obj.actor else "TEBELO"


class IncidentSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    priority = serializers.CharField(read_only=True)
    timeline = IncidentEventSerializer(many=True, read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Incident
        fields = ("id", "reference", "category", "category_name", "description", "address", "latitude", "longitude", "occurred_at", "anonymous", "status", "priority", "created_at", "updated_at", "timeline")
        read_only_fields = ("created_at", "updated_at")

    def create(self, validated_data):
        category = validated_data["category"]
        request = self.context["request"]
        with transaction.atomic():
            organisation = Organisation.objects.filter(kind=category.routes_to, is_active=True).order_by("created_at").first()
            incident = Incident.objects.create(
                reporter=request.user, priority=category.default_priority,
                assigned_organisation=organisation, **validated_data,
            )
            IncidentEvent.objects.create(incident=incident, actor=request.user, event_type="reported", to_status=incident.status)
            if organisation:
                IncidentEvent.objects.create(incident=incident, event_type="routed", note=f"Routed to {organisation.name}")
            audit(request=request, action="incident.created", obj=incident, metadata={"channel": "api"})
            return incident


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ("id", "title", "summary", "category", "severity", "scope", "location", "latitude", "longitude", "radius_km", "starts_at", "ends_at")
