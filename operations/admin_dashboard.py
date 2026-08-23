from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from .models import Alert, DeliveryCase, Incident, OperationalRecommendation, Organisation, ServiceDeskCase


def dashboard_callback(request, context):
    now = timezone.now()
    today = timezone.localdate()
    active = Incident.objects.exclude(status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED])
    recent = active.select_related("category", "assigned_organisation").order_by("-created_at")[:8]
    week_start = today - timedelta(days=6)
    raw_daily = {
        row["day"]: row["total"]
        for row in Incident.objects.filter(created_at__date__gte=week_start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
    }
    daily = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        daily.append({"label": day.strftime("%a"), "total": raw_daily.get(day, 0)})
    peak = max((item["total"] for item in daily), default=0) or 1
    for item in daily:
        item["height"] = max(5, round(item["total"] / peak * 100)) if item["total"] else 3

    organisations = Organisation.objects.filter(is_active=True).annotate(
        open_cases=Count("incidents", filter=~Q(incidents__status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED]))
    ).order_by("-open_cases", "short_name")[:6]
    priority_rows = []
    priority_counts = dict(active.values_list("priority").annotate(total=Count("id")))
    total_active = active.count()
    for value, label in Incident.Priority.choices:
        count = priority_counts.get(value, 0)
        priority_rows.append({"value": value, "label": label, "count": count, "percent": round(count / total_active * 100) if total_active else 0})

    context.update({
        "ops": {
            "active": total_active,
            "critical": priority_counts.get(Incident.Priority.CRITICAL, 0),
            "reported_today": Incident.objects.filter(created_at__date=today).count(),
            "resolved_today": Incident.objects.filter(resolved_at__date=today).count(),
            "unverified": Incident.objects.filter(status__in=[Incident.Status.REPORTED, Incident.Status.TRIAGED]).count(),
            "open_desks": ServiceDeskCase.objects.filter(is_closed=False).count(),
            "active_alerts": Alert.objects.filter(is_published=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)).count(),
            "delivery_overdue": DeliveryCase.objects.exclude(stage__in=["resolved", "closed"]).filter(
                Q(acknowledged_at__isnull=True, acknowledgement_due_at__lt=now)
                | Q(resolution_due_at__lt=now)
            ).count(),
            "recommendations": OperationalRecommendation.objects.filter(status="proposed").count(),
        },
        "recent_incidents": recent,
        "daily_incidents": daily,
        "priority_rows": priority_rows,
        "organisation_load": organisations,
        "incident_changelist_url": reverse("admin:operations_incident_changelist"),
        "alert_add_url": reverse("admin:operations_alert_add"),
        "delivery_engine_url": reverse("admin_delivery_engine"),
        "updated_at": now,
    })
    return context
