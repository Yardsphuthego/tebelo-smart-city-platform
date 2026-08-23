from datetime import timedelta
import math
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from core.models import audit
from .forms import (
    AlertForm,
    AuthorityHandoffForm,
    IncidentReportForm,
    IncidentUpdateForm,
    NeighborhoodWatchGroupForm,
    ServiceDeskForm,
)
from .models import (
    Alert,
    AuthorityHandoff,
    AuthorityNotification,
    DeliveryCase,
    DeliveryEvent,
    DutyShift,
    Evidence,
    Incident,
    NeighborhoodWatchGroup,
    NeighborhoodWatchMembership,
    OperationalRecommendation,
    Organisation,
    ServiceDeskCase,
    ServiceMessage,
)
from .delivery import (
    process_due_delivery_cases,
    refresh_operational_recommendations,
    request_handoff,
    respond_handoff,
)
from .permissions import can_manage_incident
from .services import create_incident, distance_km, update_incident


def _authority_incidents(user):
    qs = Incident.objects.select_related("category", "location", "assigned_organisation", "assigned_to")
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        return qs
    orgs = user.memberships.filter(is_active=True).values("organisation_id")
    return qs.filter(assigned_organisation_id__in=orgs)


def _city_overview_context(request):
    now = timezone.now()
    alerts = Alert.objects.filter(is_published=True, starts_at__lte=now).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))[:4]
    active = Incident.objects.filter(is_public=True).exclude(status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED])
    critical_count = active.filter(priority=Incident.Priority.CRITICAL).count()
    high_count = active.filter(priority=Incident.Priority.HIGH).count()
    if critical_count:
        city_status, status_detail = "Critical", "Critical incidents require attention"
    elif high_count >= 3:
        city_status, status_detail = "Elevated", "Increased activity across the city"
    else:
        city_status, status_detail = "Normal", "No unusual public activity detected"
    city_metrics = {
        "active": active.count(),
        "critical": critical_count,
        "safety": active.filter(category__domain="safety").count(),
        "traffic": active.filter(category__domain="traffic").count(),
        "services": active.filter(category__domain__in=["utilities", "infrastructure"]).count(),
    }
    reports = request.user.reported_incidents.all()[:4] if request.user.is_authenticated else []
    return {
        "alerts": alerts, "reports": reports, "city_metrics": city_metrics,
        "city_status": city_status, "status_detail": status_detail, "updated_at": now,
    }


def home(request):
    return render(request, "operations/landing.html", _city_overview_context(request))


@login_required
def dashboard(request):
    if request.user.is_superuser:
        return redirect("admin:index")
    if request.user.is_authority:
        return redirect("command_dashboard")
    return render(request, "operations/dashboard_home.html", _city_overview_context(request))


@login_required
def report_incident(request):
    initial = {}
    requested_group = request.GET.get("watch_group")
    if requested_group and request.user.watch_memberships.filter(
        group_id=requested_group,
        group__status=NeighborhoodWatchGroup.Status.ACTIVE,
        status=NeighborhoodWatchMembership.Status.ACTIVE,
    ).exists():
        initial["watch_group"] = requested_group
    form = IncidentReportForm(
        request.POST or None, request.FILES or None, user=request.user, initial=initial
    )
    if request.method == "POST" and form.is_valid():
        incident = create_incident(form=form, user=request.user, request=request)
        messages.success(request, f"Report {incident.reference} was received and securely recorded.")
        return redirect("incident_detail", pk=incident.pk)
    return render(request, "operations/report_form.html", {"form": form})


@login_required
def my_reports(request):
    incidents = request.user.reported_incidents.select_related("category", "assigned_organisation")
    return render(request, "operations/my_reports.html", {"incidents": incidents})


def incident_detail(request, pk):
    incident = get_object_or_404(Incident.objects.select_related("category", "assigned_organisation", "assigned_to"), pk=pk)
    owner = request.user.is_authenticated and incident.reporter_id == request.user.id
    manager = request.user.is_authenticated and can_manage_incident(request.user, incident)
    if not (incident.is_public or owner or manager):
        raise PermissionDenied
    return render(request, "operations/incident_detail.html", {"incident": incident, "owner": owner, "manager": manager})


def city_map(request):
    return render(request, "operations/map.html")


def public_incidents_geojson(request):
    incidents = Incident.objects.filter(is_public=True).exclude(status__in=[Incident.Status.REJECTED, Incident.Status.CLOSED]).select_related("category")[:1000]
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(i.longitude), float(i.latitude)]},
        "properties": {"id": str(i.id), "reference": i.reference, "category": i.category.name, "domain": i.category.domain,
                       "summary": i.public_summary or "An incident has been reported in this area.", "status": i.get_status_display(),
                       "priority": i.priority, "reported_at": i.created_at.isoformat()},
    } for i in incidents]
    return JsonResponse({"type": "FeatureCollection", "features": features})


def public_watch_groups_geojson(request):
    groups = NeighborhoodWatchGroup.objects.filter(
        status=NeighborhoodWatchGroup.Status.ACTIVE, is_map_visible=True
    ).select_related("area").annotate(
        member_count=Count(
            "memberships",
            filter=Q(memberships__status=NeighborhoodWatchMembership.Status.ACTIVE),
            distinct=True,
        )
    )[:500]
    features = []
    for group in groups:
        properties = {
            "id": str(group.id),
            "reference": group.reference,
            "name": group.name,
            "area": group.area.name,
            "radius_km": float(group.radius_km),
            "member_count": group.member_count,
            "url": request.build_absolute_uri(reverse("watch_group_detail", args=[group.pk])),
        }
        latitude = math.radians(float(group.centre_latitude))
        longitude = math.radians(float(group.centre_longitude))
        angular_radius = float(group.radius_km) / 6371.0088
        ring = []
        for step in range(65):
            bearing = math.radians(step * 360 / 64)
            point_latitude = math.asin(
                math.sin(latitude) * math.cos(angular_radius)
                + math.cos(latitude) * math.sin(angular_radius) * math.cos(bearing)
            )
            point_longitude = longitude + math.atan2(
                math.sin(bearing) * math.sin(angular_radius) * math.cos(latitude),
                math.cos(angular_radius) - math.sin(latitude) * math.sin(point_latitude),
            )
            ring.append([math.degrees(point_longitude), math.degrees(point_latitude)])
        features.extend((
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {**properties, "feature_kind": "coverage"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(group.centre_longitude), float(group.centre_latitude)],
                },
                "properties": {**properties, "feature_kind": "centre"},
            },
        ))
    return JsonResponse({"type": "FeatureCollection", "features": features})


def alerts(request):
    active = Alert.objects.filter(is_published=True, starts_at__lte=timezone.now()).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
    return render(request, "operations/alerts.html", {"alerts": active})


def around_me(request):
    nearby = []
    lat = request.GET.get("lat")
    lon = request.GET.get("lon")
    radius = min(float(request.GET.get("radius", 3)), 25) if request.GET.get("radius", "3").replace(".", "", 1).isdigit() else 3
    if lat and lon:
        try:
            latitude, longitude = float(lat), float(lon)
            candidates = Incident.objects.filter(is_public=True, created_at__gte=timezone.now() - timedelta(days=7)).select_related("category")[:2000]
            nearby = [(i, distance_km(latitude, longitude, i.latitude, i.longitude)) for i in candidates]
            nearby = sorted((x for x in nearby if x[1] <= radius), key=lambda x: x[1])
        except (ValueError, TypeError):
            messages.error(request, "The supplied location was invalid.")
    counts = {}
    for incident, _distance in nearby:
        counts[incident.category.domain] = counts.get(incident.category.domain, 0) + 1
    return render(request, "operations/around_me.html", {"nearby": nearby, "counts": counts, "latitude": lat, "longitude": lon, "radius": radius})


@login_required
def evidence_download(request, pk):
    evidence = get_object_or_404(Evidence.objects.select_related("incident"), pk=pk)
    if evidence.incident.reporter_id != request.user.id and not can_manage_incident(request.user, evidence.incident):
        raise PermissionDenied
    audit(request=request, action="evidence.accessed", obj=evidence, metadata={"incident": evidence.incident.reference})
    response = FileResponse(evidence.file.open("rb"), content_type=evidence.content_type)
    response["Content-Disposition"] = f'attachment; filename="{evidence.original_name.replace(chr(34), "")}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def command_dashboard(request):
    if not request.user.is_authority:
        raise PermissionDenied
    qs = _authority_incidents(request.user)
    today = timezone.localdate()
    metrics = {
        "active": qs.exclude(status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED]).count(),
        "critical": qs.filter(priority=Incident.Priority.CRITICAL).exclude(status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED]).count(),
        "today": qs.filter(created_at__date=today).count(),
        "resolved": qs.filter(resolved_at__date=today).count(),
    }
    queue = qs.exclude(status__in=[Incident.Status.CLOSED, Incident.Status.REJECTED]).order_by("-priority", "created_at")[:50]
    categories = qs.filter(created_at__gte=timezone.now() - timedelta(days=30)).values("category__name").annotate(total=Count("id")).order_by("-total")[:8]
    return render(request, "operations/dashboard.html", {"metrics": metrics, "queue": queue, "categories": categories})


@login_required
def manage_incident(request, pk):
    incident = get_object_or_404(_authority_incidents(request.user), pk=pk)
    if not can_manage_incident(request.user, incident):
        raise PermissionDenied
    form = IncidentUpdateForm(request.POST or None, instance=incident)
    permitted_orgs = request.user.memberships.filter(is_active=True).values_list("organisation_id", flat=True)
    if not (request.user.is_superuser or request.user.role in {request.user.Role.COMMAND, request.user.Role.ADMIN}):
        form.fields["assigned_organisation"].queryset = form.fields["assigned_organisation"].queryset.filter(id__in=permitted_orgs)
        form.fields["assigned_to"].queryset = form.fields["assigned_to"].queryset.filter(memberships__organisation_id__in=permitted_orgs, memberships__is_active=True).distinct()
    if request.method == "POST" and form.is_valid():
        if update_incident(incident=incident, form=form, user=request.user, request=request):
            messages.success(request, "Incident updated and added to the audit trail.")
            return redirect("manage_incident", pk=incident.pk)
    return render(request, "operations/manage_incident.html", {"incident": incident, "form": form})


@login_required
def create_alert(request):
    if request.user.role not in {request.user.Role.COMMAND, request.user.Role.ADMIN} and not request.user.is_superuser:
        raise PermissionDenied
    form = AlertForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        alert = form.save(commit=False)
        alert.published_by = request.user
        alert.save()
        audit(request=request, action="alert.created", obj=alert, metadata={"published": alert.is_published})
        messages.success(request, "The city alert has been saved.")
        return redirect("alerts")
    return render(request, "operations/alert_form.html", {"form": form})


@login_required
def service_desks(request):
    cases = request.user.service_cases.select_related("assigned_organisation", "assigned_to")[:20]
    selected_desk = request.GET.get("desk", ServiceDeskCase.Desk.POLICE)
    if selected_desk not in ServiceDeskCase.Desk.values:
        selected_desk = ServiceDeskCase.Desk.POLICE
    form = ServiceDeskForm(request.POST or None, initial={"desk": selected_desk})
    form.fields["incident"].queryset = request.user.reported_incidents.all()
    if request.method == "POST" and form.is_valid():
        case = form.save(commit=False)
        case.resident = request.user
        organisation_kind = {
            ServiceDeskCase.Desk.POLICE: Organisation.Kind.POLICE,
            ServiceDeskCase.Desk.GOVERNMENT: Organisation.Kind.COUNCIL,
            ServiceDeskCase.Desk.TRAFFIC: Organisation.Kind.TRAFFIC,
            ServiceDeskCase.Desk.FIRE: Organisation.Kind.FIRE,
        }[case.desk]
        case.assigned_organisation = Organisation.objects.filter(
            kind=organisation_kind, is_active=True
        ).first()
        if case.assigned_organisation:
            case.status = ServiceDeskCase.Status.ROUTED
        case.save()
        ServiceMessage.objects.create(case=case, sender=request.user, body=form.cleaned_data["message"])
        audit(
            request=request,
            action="service_case.created",
            obj=case,
            metadata={"desk": case.desk, "reference": case.reference, "organisation": str(case.assigned_organisation_id or "")},
        )
        messages.success(request, f"Virtual service case {case.reference} has been opened.")
        return redirect("service_case", pk=case.pk)
    return render(request, "operations/service_desks.html", {
        "form": form, "cases": cases, "selected_desk": selected_desk,
    })


@login_required
def service_case(request, pk):
    case = get_object_or_404(ServiceDeskCase.objects.prefetch_related("messages__sender"), pk=pk)
    if not _can_access_service_case(request.user, case):
        raise PermissionDenied
    return render(request, "operations/service_case.html", {"case": case})


@login_required
@require_POST
def service_message(request, pk):
    case = get_object_or_404(ServiceDeskCase, pk=pk)
    if not _can_access_service_case(request.user, case):
        raise PermissionDenied
    body = request.POST.get("body", "").strip()
    if body and len(body) <= 2000 and not case.is_closed:
        ServiceMessage.objects.create(case=case, sender=request.user, body=body)
        audit(request=request, action="service_message.sent", obj=case)
    return redirect("service_case", pk=case.pk)


def watch_groups(request):
    groups = list(NeighborhoodWatchGroup.objects.filter(
        status=NeighborhoodWatchGroup.Status.ACTIVE
    ).select_related("area", "police_organisation").annotate(
        member_count=Count(
            "memberships",
            filter=Q(memberships__status=NeighborhoodWatchMembership.Status.ACTIVE),
            distinct=True,
        ),
        report_count=Count("incidents", distinct=True),
    ))
    memberships = {}
    created_groups = NeighborhoodWatchGroup.objects.none()
    if request.user.is_authenticated:
        memberships = {
            str(item.group_id): item
            for item in request.user.watch_memberships.select_related("group")
        }
        created_groups = request.user.created_watch_groups.exclude(
            status=NeighborhoodWatchGroup.Status.ACTIVE
        ).select_related("area")
        for group in groups:
            group.current_membership = memberships.get(str(group.pk))
    return render(request, "operations/watch_groups.html", {
        "groups": groups, "memberships": memberships, "created_groups": created_groups,
    })


@login_required
def watch_group_create(request):
    form = NeighborhoodWatchGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.created_by = request.user
        group.police_organisation = Organisation.objects.filter(
            kind=Organisation.Kind.POLICE, is_active=True
        ).first()
        group.save()
        NeighborhoodWatchMembership.objects.create(
            group=group,
            user=request.user,
            role=NeighborhoodWatchMembership.Role.COORDINATOR,
        )
        audit(request=request, action="watch_group.created", obj=group, metadata={"reference": group.reference})
        messages.success(request, f"Watch group {group.reference} was submitted for police review.")
        return redirect("watch_group_detail", pk=group.pk)
    return render(request, "operations/watch_group_form.html", {"form": form})


def watch_group_detail(request, pk):
    group = get_object_or_404(
        NeighborhoodWatchGroup.objects.select_related("area", "police_organisation", "created_by").annotate(
            member_count=Count(
                "memberships",
                filter=Q(memberships__status=NeighborhoodWatchMembership.Status.ACTIVE),
                distinct=True,
            ),
            report_count=Count("incidents", distinct=True),
        ),
        pk=pk,
    )
    membership = None
    manager = False
    if request.user.is_authenticated:
        membership = NeighborhoodWatchMembership.objects.filter(group=group, user=request.user).first()
        manager = _can_manage_watch_group(request.user, group)
    if group.status != NeighborhoodWatchGroup.Status.ACTIVE and not (
        request.user.is_authenticated and (group.created_by_id == request.user.id or membership or manager)
    ):
        raise PermissionDenied
    reports = group.incidents.filter(is_public=True).select_related("category")[:10]
    if manager:
        reports = group.incidents.select_related("category")[:20]
    elif request.user.is_authenticated and membership and membership.status == NeighborhoodWatchMembership.Status.ACTIVE:
        reports = group.incidents.filter(
            Q(is_public=True) | Q(reporter=request.user)
        ).select_related("category")[:20]
    return render(request, "operations/watch_group_detail.html", {
        "group": group, "membership": membership, "manager": manager, "reports": reports,
    })


@login_required
@require_POST
def watch_group_join(request, pk):
    group = get_object_or_404(NeighborhoodWatchGroup, pk=pk, status=NeighborhoodWatchGroup.Status.ACTIVE)
    membership, created = NeighborhoodWatchMembership.objects.get_or_create(
        group=group, user=request.user,
        defaults={"status": NeighborhoodWatchMembership.Status.PENDING},
    )
    if not created and membership.status in {
        NeighborhoodWatchMembership.Status.DECLINED,
        NeighborhoodWatchMembership.Status.LEFT,
    }:
        membership.status = NeighborhoodWatchMembership.Status.PENDING
        membership.reviewed_by = None
        membership.reviewed_at = None
        membership.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    audit(request=request, action="watch_membership.requested", obj=group)
    messages.success(request, "Your membership request was sent for police review.")
    return redirect("watch_group_detail", pk=group.pk)


@login_required
@require_POST
def watch_group_leave(request, pk):
    membership = get_object_or_404(
        NeighborhoodWatchMembership, group_id=pk, user=request.user,
        status=NeighborhoodWatchMembership.Status.ACTIVE,
    )
    membership.status = NeighborhoodWatchMembership.Status.LEFT
    membership.save(update_fields=("status", "updated_at"))
    audit(request=request, action="watch_membership.left", obj=membership.group)
    messages.success(request, "You have left this Neighborhood Watch group.")
    return redirect("watch_group_detail", pk=membership.group_id)


@login_required
def watch_command(request):
    if not _can_manage_watch_groups(request.user):
        raise PermissionDenied
    groups = _managed_watch_groups(request.user).select_related(
        "area", "police_organisation", "created_by"
    ).annotate(
        member_count=Count("memberships", filter=Q(memberships__status="active"), distinct=True),
        pending_count=Count("memberships", filter=Q(memberships__status="pending"), distinct=True),
        report_count=Count("incidents", distinct=True),
    )
    reports = Incident.objects.filter(watch_group__in=groups).select_related(
        "watch_group", "category", "reporter", "assigned_organisation"
    )[:100]
    return render(request, "operations/watch_command.html", {"groups": groups, "reports": reports})


@login_required
@require_POST
def watch_group_action(request, pk):
    group = get_object_or_404(_managed_watch_groups(request.user), pk=pk)
    action = request.POST.get("action")
    if action == "approve":
        if not group.police_organisation_id:
            group.police_organisation = _police_organisations(request.user).first()
        group.status = NeighborhoodWatchGroup.Status.ACTIVE
        group.is_map_visible = True
        group.save()
        coordinator = group.memberships.filter(user=group.created_by).first()
        if coordinator:
            coordinator.status = NeighborhoodWatchMembership.Status.ACTIVE
            coordinator.reviewed_by = request.user
            coordinator.reviewed_at = timezone.now()
            coordinator.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    elif action == "suspend":
        group.status = NeighborhoodWatchGroup.Status.SUSPENDED
        group.save()
    elif action == "show_map" and group.status == NeighborhoodWatchGroup.Status.ACTIVE:
        group.is_map_visible = True
        group.save(update_fields=("is_map_visible", "updated_at"))
    elif action == "hide_map":
        group.is_map_visible = False
        group.save(update_fields=("is_map_visible", "updated_at"))
    else:
        raise PermissionDenied
    audit(request=request, action=f"watch_group.{action}", obj=group)
    messages.success(request, f"{group.name} was updated.")
    return redirect("watch_command")


@login_required
@require_POST
def watch_membership_action(request, pk):
    membership = get_object_or_404(NeighborhoodWatchMembership.objects.select_related("group"), pk=pk)
    if not _can_manage_watch_group(request.user, membership.group):
        raise PermissionDenied
    action = request.POST.get("action")
    if action not in {"approve", "decline"}:
        raise PermissionDenied
    membership.status = (
        NeighborhoodWatchMembership.Status.ACTIVE
        if action == "approve" else NeighborhoodWatchMembership.Status.DECLINED
    )
    membership.reviewed_by = request.user
    membership.reviewed_at = timezone.now()
    membership.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    audit(request=request, action=f"watch_membership.{action}", obj=membership.group, metadata={"member": str(membership.user_id)})
    messages.success(request, "Membership request updated.")
    return redirect("watch_group_detail", pk=membership.group_id)


@login_required
def delivery_command(request):
    if not request.user.is_authority:
        raise PermissionDenied
    if request.user.is_staff:
        return redirect("admin_delivery_engine")
    return render(request, "operations/delivery_command.html", _delivery_workspace_context(request.user))


def _delivery_workspace_context(user):
    now = timezone.now()
    process_due_delivery_cases(now)
    recommendations = refresh_operational_recommendations(now)
    cases = _delivery_cases_for_user(user).select_related(
        "incident__category", "service_case", "organisation", "assigned_to", "escalated_to"
    )
    open_cases = cases.exclude(stage__in={DeliveryCase.Stage.RESOLVED, DeliveryCase.Stage.CLOSED})
    metrics = {
        "open": open_cases.count(),
        "unassigned": open_cases.filter(organisation__isnull=True).count(),
        "unacknowledged_overdue": open_cases.filter(
            acknowledged_at__isnull=True, acknowledgement_due_at__lt=now
        ).count(),
        "resolution_overdue": open_cases.filter(resolution_due_at__lt=now).count(),
        "escalated": open_cases.filter(escalation_level__gt=0).count(),
    }
    organisation_ids = _authority_organisation_ids(user)
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        shifts = DutyShift.objects.filter(is_active=True, starts_at__lte=now, ends_at__gt=now)
        handoffs = AuthorityHandoff.objects.filter(status=AuthorityHandoff.Status.REQUESTED)
    else:
        shifts = DutyShift.objects.filter(
            organisation_id__in=organisation_ids, is_active=True, starts_at__lte=now, ends_at__gt=now
        )
        handoffs = AuthorityHandoff.objects.filter(
            to_organisation_id__in=organisation_ids, status=AuthorityHandoff.Status.REQUESTED
        )
    notifications = user.authority_notifications.filter(read_at__isnull=True)[:8]
    return {
        "metrics": metrics,
        "queue": open_cases[:100],
        "shifts": shifts.select_related("organisation").prefetch_related("assignments__user")[:12],
        "handoffs": handoffs.select_related("case__incident", "case__service_case", "from_organisation", "to_organisation")[:20],
        "recommendations": recommendations[:12],
        "notifications": notifications,
        "now": now,
    }


def admin_delivery_engine(request):
    context = admin.site.each_context(request)
    context.update(_delivery_workspace_context(request.user))
    context.update({
        "title": "Service delivery",
        "subtitle": "Routing, deadlines, escalations and authority ownership",
    })
    return render(request, "admin/delivery_engine.html", context)


def admin_delivery_case_detail(request, pk):
    case = get_object_or_404(
        _delivery_cases_for_user(request.user).select_related(
            "incident__category", "service_case", "organisation", "assigned_to", "policy", "escalated_to"
        ).prefetch_related("events__actor", "events__organisation", "handoffs"),
        pk=pk,
    )
    context = admin.site.each_context(request)
    context.update({
        "title": case.reference,
        "subtitle": case.subject,
        "delivery": case,
        "form": AuthorityHandoffForm(current_organisation=case.organisation),
        "now": timezone.now(),
    })
    return render(request, "admin/delivery_case_detail.html", context)


@login_required
def delivery_case_detail(request, pk):
    if request.user.is_staff:
        return redirect("admin_delivery_case_detail", pk=pk)
    case = get_object_or_404(
        _delivery_cases_for_user(request.user).select_related(
            "incident__category", "service_case", "organisation", "assigned_to", "policy", "escalated_to"
        ).prefetch_related("events__actor", "events__organisation", "handoffs"),
        pk=pk,
    )
    form = AuthorityHandoffForm(current_organisation=case.organisation)
    return render(request, "operations/delivery_case_detail.html", {"delivery": case, "form": form, "now": timezone.now()})


@login_required
@require_POST
def delivery_case_action(request, pk):
    case = get_object_or_404(_delivery_cases_for_user(request.user), pk=pk)
    action = request.POST.get("action")
    now = timezone.now()
    changed = []
    if action == "acknowledge":
        if not case.acknowledged_at:
            case.acknowledged_at = now
            changed.append("acknowledged_at")
        if case.stage == DeliveryCase.Stage.OPEN:
            case.stage = DeliveryCase.Stage.ACKNOWLEDGED
            changed.append("stage")
    elif action == "assign_self":
        if case.organisation_id and not _can_work_for_organisation(request.user, case.organisation_id):
            raise PermissionDenied
        case.assigned_to = request.user
        case.assigned_at = now
        case.acknowledged_at = case.acknowledged_at or now
        case.stage = DeliveryCase.Stage.ASSIGNED
        changed.extend(("assigned_to", "assigned_at", "acknowledged_at", "stage"))
        source_model = Incident if case.incident_id else ServiceDeskCase
        source_model.objects.filter(pk=case.incident_id or case.service_case_id).update(assigned_to=request.user)
    elif action == "start":
        if case.assigned_to_id not in {None, request.user.id} and not _is_command_user(request.user):
            raise PermissionDenied
        case.assigned_to = case.assigned_to or request.user
        case.assigned_at = case.assigned_at or now
        case.acknowledged_at = case.acknowledged_at or now
        case.stage = DeliveryCase.Stage.IN_PROGRESS
        changed.extend(("assigned_to", "assigned_at", "acknowledged_at", "stage"))
        if case.service_case_id:
            ServiceDeskCase.objects.filter(pk=case.service_case_id).update(
                assigned_to=case.assigned_to, status=ServiceDeskCase.Status.IN_PROGRESS
            )
    else:
        raise PermissionDenied
    case.save(update_fields=(*set(changed), "updated_at"))
    DeliveryEvent.objects.create(
        case=case, actor=request.user, organisation=case.organisation,
        event_type=action, note=request.POST.get("note", "")[:500],
    )
    audit(request=request, action=f"delivery_case.{action}", obj=case)
    messages.success(request, f"{case.reference} was updated.")
    return _safe_workflow_redirect(request, "delivery_case_detail", pk=case.pk)


@login_required
@require_POST
def delivery_handoff_request(request, pk):
    case = get_object_or_404(_delivery_cases_for_user(request.user), pk=pk)
    form = AuthorityHandoffForm(request.POST, current_organisation=case.organisation)
    if form.is_valid():
        request_handoff(
            case=case,
            to_organisation=form.cleaned_data["to_organisation"],
            user=request.user,
            reason=form.cleaned_data["reason"],
            request=request,
        )
        messages.success(request, "The receiving authority has been asked to accept this case.")
    else:
        messages.error(request, "The handoff request was incomplete.")
    return _safe_workflow_redirect(request, "delivery_case_detail", pk=case.pk)


@login_required
@require_POST
def delivery_handoff_response(request, pk):
    handoff = get_object_or_404(AuthorityHandoff.objects.select_related("case", "to_organisation"), pk=pk)
    if not (
        _is_command_user(request.user)
        or _can_work_for_organisation(request.user, handoff.to_organisation_id)
    ):
        raise PermissionDenied
    decision = request.POST.get("decision")
    if decision not in {"accept", "decline"}:
        raise PermissionDenied
    respond_handoff(
        handoff=handoff,
        user=request.user,
        accept=decision == "accept",
        note=request.POST.get("note", "")[:1000],
        request=request,
    )
    messages.success(request, f"Handoff {decision}ed.")
    return _safe_workflow_redirect(request, "delivery_command")


@login_required
@require_POST
def recommendation_action(request, pk):
    if not _is_command_user(request.user):
        raise PermissionDenied
    recommendation = get_object_or_404(OperationalRecommendation, pk=pk)
    status = request.POST.get("status")
    if status not in OperationalRecommendation.Status.values:
        raise PermissionDenied
    recommendation.status = status
    recommendation.save(update_fields=("status", "updated_at"))
    audit(request=request, action=f"recommendation.{status}", obj=recommendation)
    messages.success(request, "Recommendation status updated.")
    return _safe_workflow_redirect(request, "delivery_command")


@login_required
@require_POST
def notification_read(request, pk):
    notification = get_object_or_404(AuthorityNotification, pk=pk, user=request.user)
    notification.read_at = timezone.now()
    notification.save(update_fields=("read_at", "updated_at"))
    return _safe_workflow_redirect(request, "delivery_command")


def emergency(request):
    return render(request, "operations/emergency.html")


def _can_access_service_case(user, case):
    if case.resident_id == user.id:
        return True
    if not user.is_authority:
        return False
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        return True
    if case.assigned_to_id == user.id:
        return True
    if case.assigned_organisation_id:
        return user.memberships.filter(
            is_active=True, organisation_id=case.assigned_organisation_id
        ).exists()
    return user.memberships.filter(is_active=True, organisation__kind=case.desk).exists()


def _police_organisations(user):
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        return Organisation.objects.filter(kind=Organisation.Kind.POLICE, is_active=True)
    return Organisation.objects.filter(
        kind=Organisation.Kind.POLICE,
        is_active=True,
        memberships__user=user,
        memberships__is_active=True,
    ).distinct()


def _can_manage_watch_groups(user):
    return user.is_authority and (
        user.is_superuser
        or user.role in {user.Role.COMMAND, user.Role.ADMIN}
        or _police_organisations(user).exists()
    )


def _safe_workflow_redirect(request, default_name, **kwargs):
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default_name, **kwargs)


def _managed_watch_groups(user):
    groups = NeighborhoodWatchGroup.objects.all()
    if user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}:
        return groups
    organisations = _police_organisations(user)
    return groups.filter(Q(police_organisation__in=organisations) | Q(police_organisation__isnull=True))


def _can_manage_watch_group(user, group):
    return _can_manage_watch_groups(user) and _managed_watch_groups(user).filter(pk=group.pk).exists()


def _is_command_user(user):
    return user.is_superuser or user.role in {user.Role.COMMAND, user.Role.ADMIN}


def _authority_organisation_ids(user):
    return user.memberships.filter(is_active=True).values_list("organisation_id", flat=True)


def _can_work_for_organisation(user, organisation_id):
    return _is_command_user(user) or user.memberships.filter(
        is_active=True, organisation_id=organisation_id
    ).exists()


def _delivery_cases_for_user(user):
    cases = DeliveryCase.objects.all()
    if _is_command_user(user):
        return cases
    if not user.is_authority:
        return cases.none()
    organisations = _authority_organisation_ids(user)
    return cases.filter(
        Q(organisation_id__in=organisations)
        | Q(escalated_to_id__in=organisations)
        | Q(handoffs__to_organisation_id__in=organisations, handoffs__status=AuthorityHandoff.Status.REQUESTED)
        | Q(assigned_to=user)
    ).distinct()
