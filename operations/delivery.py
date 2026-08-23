from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.models import audit
from .models import (
    AuthorityHandoff,
    AuthorityNotification,
    DeliveryCase,
    DeliveryEvent,
    DutyAssignment,
    DutyShift,
    Incident,
    Membership,
    NeighborhoodWatchGroup,
    OperationalRecommendation,
    Organisation,
    ServiceDeskCase,
    ServiceRoutingPolicy,
)


def ensure_command_coverage():
    """Maintain today's command-centre shift for authorised platform administrators."""
    command_org = Organisation.objects.filter(short_name="TEBELO-CMD", is_active=True).first()
    if not command_org:
        return None

    local_now = timezone.localtime()
    starts_at = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    ends_at = starts_at + timedelta(days=1)
    shift, _ = DutyShift.objects.update_or_create(
        organisation=command_org,
        name=f"Command oversight · {starts_at.date().isoformat()}",
        defaults={"starts_at": starts_at, "ends_at": ends_at, "is_active": True},
    )
    users = get_user_model().objects.filter(is_active=True, is_superuser=True)
    for user in users:
        Membership.objects.update_or_create(
            user=user,
            organisation=command_org,
            defaults={"role": Membership.Role.ADMIN, "is_active": True},
        )
        DutyAssignment.objects.update_or_create(
            shift=shift,
            user=user,
            defaults={"role": DutyAssignment.Role.SUPERVISOR, "is_available": True},
        )
    return shift


DEFAULT_INCIDENT_SLA = {
    Incident.Priority.CRITICAL: (5, 10, 240),
    Incident.Priority.HIGH: (15, 30, 720),
    Incident.Priority.MEDIUM: (30, 60, 1440),
    Incident.Priority.LOW: (60, 240, 4320),
}
DEFAULT_SERVICE_SLA = (60, 240, 2880)


def _matching_policy(source):
    policies = ServiceRoutingPolicy.objects.filter(is_active=True)
    if isinstance(source, Incident):
        policies = policies.filter(
            case_type=ServiceRoutingPolicy.CaseType.INCIDENT
        ).filter(
            Q(incident_category__isnull=True) | Q(incident_category=source.category),
            Q(incident_priority="") | Q(incident_priority=source.priority),
        )
        for policy in policies.select_related("destination_organisation", "escalation_organisation"):
            if policy.incident_category_id in {None, source.category_id}:
                return policy
    else:
        policies = policies.filter(
            case_type=ServiceRoutingPolicy.CaseType.VIRTUAL_SERVICE
        ).filter(
            Q(service_desk="") | Q(service_desk=source.desk),
            Q(service_request_type="") | Q(service_request_type=source.request_type),
        )
        for policy in policies.select_related("destination_organisation", "escalation_organisation"):
            if policy.service_desk in {"", source.desk} and policy.service_request_type in {"", source.request_type}:
                return policy
    return None


def _active_duty_user(organisation, now):
    if not organisation:
        return None
    assignment = DutyAssignment.objects.filter(
        shift__organisation=organisation,
        shift__is_active=True,
        shift__starts_at__lte=now,
        shift__ends_at__gt=now,
        is_available=True,
        user__memberships__organisation=organisation,
        user__memberships__is_active=True,
    ).select_related("user").order_by("role", "created_at").first()
    return assignment.user if assignment else None


@transaction.atomic
def register_delivery_case(source):
    if not isinstance(source, (Incident, ServiceDeskCase)):
        raise TypeError("Delivery cases can only be registered for incidents or virtual-service cases.")
    relation = "incident" if isinstance(source, Incident) else "service_case"
    existing = DeliveryCase.objects.filter(**{relation: source}).first()
    if existing:
        return sync_delivery_case(existing, source)

    now = timezone.now()
    policy = _matching_policy(source)
    if policy:
        sla = (
            policy.acknowledgement_minutes,
            policy.assignment_minutes,
            policy.resolution_minutes,
        )
        organisation = policy.destination_organisation
    elif isinstance(source, Incident):
        sla = DEFAULT_INCIDENT_SLA[source.priority]
        organisation = source.assigned_organisation
    else:
        sla = DEFAULT_SERVICE_SLA
        organisation = source.assigned_organisation
    assignee = _active_duty_user(organisation, now)
    case = DeliveryCase.objects.create(
        **{relation: source},
        policy=policy,
        organisation=organisation,
        assigned_to=assignee,
        stage=DeliveryCase.Stage.ASSIGNED if assignee else DeliveryCase.Stage.OPEN,
        acknowledgement_due_at=now + timedelta(minutes=sla[0]),
        assignment_due_at=now + timedelta(minutes=sla[1]),
        resolution_due_at=now + timedelta(minutes=sla[2]),
        assigned_at=now if assignee else None,
    )
    if organisation and source.assigned_organisation_id != organisation.id:
        type(source).objects.filter(pk=source.pk).update(assigned_organisation=organisation)
    if assignee and source.assigned_to_id != assignee.id:
        type(source).objects.filter(pk=source.pk).update(assigned_to=assignee)
    DeliveryEvent.objects.create(
        case=case,
        organisation=organisation,
        event_type="registered",
        note="Service-delivery clocks started.",
        metadata={"policy": policy.name if policy else "default"},
    )
    if assignee:
        _notify(
            assignee, case, AuthorityNotification.Kind.ASSIGNMENT,
            f"New assignment · {case.reference}",
            f"{case.subject} was assigned from the active duty shift.",
        )
    return case


def sync_delivery_case(case, source=None):
    source = source or case.source
    changed = []
    if source.assigned_organisation_id != case.organisation_id:
        case.organisation = source.assigned_organisation
        changed.append("organisation")
    if source.assigned_to_id != case.assigned_to_id:
        case.assigned_to = source.assigned_to
        case.assigned_at = case.assigned_at or timezone.now() if source.assigned_to_id else None
        changed.extend(("assigned_to", "assigned_at"))
    if isinstance(source, Incident):
        if source.status == Incident.Status.CLOSED:
            stage = DeliveryCase.Stage.CLOSED
        elif source.status == Incident.Status.RESOLVED:
            stage = DeliveryCase.Stage.RESOLVED
        elif source.status in {Incident.Status.DISPATCHED, Incident.Status.ON_SCENE}:
            stage = DeliveryCase.Stage.IN_PROGRESS
        elif source.assigned_to_id:
            stage = DeliveryCase.Stage.ASSIGNED
        else:
            stage = case.stage
    else:
        stage = {
            ServiceDeskCase.Status.IN_PROGRESS: DeliveryCase.Stage.IN_PROGRESS,
            ServiceDeskCase.Status.RESOLVED: DeliveryCase.Stage.RESOLVED,
            ServiceDeskCase.Status.CLOSED: DeliveryCase.Stage.CLOSED,
        }.get(source.status, DeliveryCase.Stage.ASSIGNED if source.assigned_to_id else case.stage)
    if stage != case.stage:
        case.stage = stage
        changed.append("stage")
    if stage in {DeliveryCase.Stage.RESOLVED, DeliveryCase.Stage.CLOSED} and not case.resolved_at:
        case.resolved_at = timezone.now()
        changed.append("resolved_at")
    if changed:
        case.save(update_fields=(*set(changed), "updated_at"))
    return case


def _notify(user, case, kind, title, body):
    return AuthorityNotification.objects.create(
        user=user, delivery_case=case, kind=kind, title=title, body=body
    )


def _supervisor_ids(organisation):
    if not organisation:
        return []
    return Membership.objects.filter(
        organisation=organisation,
        is_active=True,
        role__in={Membership.Role.SUPERVISOR, Membership.Role.ADMIN, Membership.Role.DISPATCHER},
    ).values_list("user_id", flat=True)


@transaction.atomic
def process_due_delivery_cases(now=None):
    now = now or timezone.now()
    escalated = 0
    cases = DeliveryCase.objects.exclude(
        stage__in={DeliveryCase.Stage.RESOLVED, DeliveryCase.Stage.CLOSED}
    ).select_related("incident__category", "service_case", "policy", "organisation")
    for case in cases:
        if not case.acknowledged_at and case.acknowledgement_due_at <= now:
            breach = "acknowledgement"
        elif not case.assigned_to_id and case.assignment_due_at <= now:
            breach = "assignment"
        elif case.resolution_due_at <= now:
            breach = "resolution"
        else:
            continue
        repeat_minutes = case.policy.repeat_escalation_minutes if case.policy else 30
        if case.last_escalated_at and case.last_breach == breach and (
            case.last_escalated_at + timedelta(minutes=repeat_minutes) > now
        ):
            continue
        escalation_org = case.policy.escalation_organisation if case.policy else case.organisation
        case.escalated_to = escalation_org
        case.escalation_level += 1
        case.last_escalated_at = now
        case.last_breach = breach
        case.save(update_fields=(
            "escalated_to", "escalation_level", "last_escalated_at", "last_breach", "updated_at"
        ))
        DeliveryEvent.objects.create(
            case=case,
            organisation=escalation_org,
            event_type="sla_escalated",
            note=f"{breach.title()} deadline breached.",
            metadata={"level": case.escalation_level},
        )
        for user_id in _supervisor_ids(escalation_org or case.organisation):
            AuthorityNotification.objects.create(
                user_id=user_id,
                delivery_case=case,
                kind=AuthorityNotification.Kind.SLA_BREACH,
                title=f"SLA breach · {case.reference}",
                body=f"The {breach} deadline has passed. Escalation level {case.escalation_level}.",
            )
        audit(
            action="delivery_case.escalated",
            obj=case,
            metadata={"breach": breach, "level": case.escalation_level},
        )
        escalated += 1
    return escalated


@transaction.atomic
def request_handoff(*, case, to_organisation, user, reason, request=None):
    handoff = AuthorityHandoff.objects.create(
        case=case,
        from_organisation=case.organisation,
        to_organisation=to_organisation,
        requested_by=user,
        reason=reason,
    )
    DeliveryEvent.objects.create(
        case=case, actor=user, organisation=to_organisation,
        event_type="handoff_requested", note=reason,
    )
    for user_id in _supervisor_ids(to_organisation):
        AuthorityNotification.objects.create(
            user_id=user_id, delivery_case=case, kind=AuthorityNotification.Kind.HANDOFF,
            title=f"Handoff requested · {case.reference}",
            body=f"{case.organisation or 'Central routing'} requests transfer to {to_organisation.short_name}.",
        )
    audit(request=request, actor=user, action="delivery_handoff.requested", obj=handoff)
    return handoff


@transaction.atomic
def respond_handoff(*, handoff, user, accept, note="", request=None):
    if handoff.status != AuthorityHandoff.Status.REQUESTED:
        return handoff
    handoff.status = AuthorityHandoff.Status.ACCEPTED if accept else AuthorityHandoff.Status.DECLINED
    handoff.responded_by = user
    handoff.responded_at = timezone.now()
    handoff.response_note = note
    handoff.save(update_fields=("status", "responded_by", "responded_at", "response_note", "updated_at"))
    if accept:
        case = handoff.case
        case.organisation = handoff.to_organisation
        case.assigned_to = _active_duty_user(handoff.to_organisation, timezone.now())
        case.assigned_at = timezone.now() if case.assigned_to_id else None
        case.stage = DeliveryCase.Stage.ASSIGNED if case.assigned_to_id else DeliveryCase.Stage.ACKNOWLEDGED
        case.save(update_fields=("organisation", "assigned_to", "assigned_at", "stage", "updated_at"))
        source_model = Incident if case.incident_id else ServiceDeskCase
        source_model.objects.filter(pk=case.incident_id or case.service_case_id).update(
            assigned_organisation=handoff.to_organisation,
            assigned_to=case.assigned_to,
        )
    DeliveryEvent.objects.create(
        case=handoff.case, actor=user, organisation=handoff.to_organisation,
        event_type=f"handoff_{handoff.status}", note=note,
    )
    audit(request=request, actor=user, action=f"delivery_handoff.{handoff.status}", obj=handoff)
    return handoff


STRATEGIC_RECOMMENDATIONS = (
    {
        "fingerprint": "strategy-city-town-pilot-rollout",
        "category": "rollout", "priority": "high",
        "title": "Launch one controlled city or town pilot at a time",
        "summary": "Activate public routing only after the selected local command team, authority officers, shifts, escalation contacts and response exercise have passed readiness review.",
        "source_label": "SmartBots public-sector transformation",
        "source_url": "https://smartbots.gov.bw/node/77",
    },
    {
        "fingerprint": "strategy-authority-identity-mfa",
        "category": "authority_security", "priority": "high",
        "title": "Require verified identity and MFA for authority users",
        "summary": "Keep resident phone access simple, while police, dispatchers, supervisors and administrators use verified authority enrolment plus a second authentication factor.",
        "source_label": "Botswana Data Protection Act implementation guidance",
        "source_url": "https://dailynews.gov.bw/common_up/dailynews/dailynews_pdf/18-11-2025_07-26-44_1763443604_dailynews_pdf.pdf",
    },
    {
        "fingerprint": "strategy-survivor-safe-gbv",
        "category": "survivor_safety", "priority": "high",
        "title": "Establish a survivor-safe GBV and child-protection route",
        "summary": "Use neutral notifications, safe callback windows, specialist access and multi-agency referral without exposing sensitive reports in ordinary queues.",
        "source_label": "Botswana Police Service 2024 Annual Report",
        "source_url": "https://www.police.gov.bw/images/publications/Annual_Report_final2024.pdf",
    },
    {
        "fingerprint": "strategy-road-safety-hotspots",
        "category": "road_safety", "priority": "high",
        "title": "Operationalise road-safety hotspot response",
        "summary": "Combine crash, near-miss, speeding, lighting and road-hazard reports into timed patrol and repair recommendations.",
        "source_label": "Statistics Botswana Transport Report 2024",
        "source_url": "https://www.statsbots.org.bw/sites/default/files/Transport%20and%20Infrastructure%20Statistics%20Report%202024.pdf",
    },
    {
        "fingerprint": "strategy-assisted-low-data-access",
        "category": "digital_access", "priority": "medium",
        "title": "Add assisted and low-bandwidth service channels",
        "summary": "Connect web, USSD, SMS, call-centre and kgotla-assisted access to the same case record so residents do not restart requests.",
        "source_label": "SmartBots public-sector transformation",
        "source_url": "https://smartbots.gov.bw/node/77",
    },
    {
        "fingerprint": "strategy-government-service-catalogue",
        "category": "city_services", "priority": "medium",
        "title": "Maintain an independent city and town service directory",
        "summary": "Publish each local service desk, responsibility, contact point, operating hours and verification date directly inside the TEBELO city and town operating platform.",
        "source_label": "Government of Botswana local-authority directory",
        "source_url": "https://www.gov.bw/local-authorities-view",
    },
    {
        "fingerprint": "strategy-emergency-dispatch-boundary",
        "category": "dispatch", "priority": "high",
        "title": "Connect verified cases to dispatch without replacing emergency lines",
        "summary": "Provide an authorised dispatcher bridge and clear escalation rules while preserving 999 for police, 998 for fire and 997 for ambulance emergencies.",
        "source_label": "Botswana Police Service emergency guidance",
        "source_url": "https://www.police.gov.bw/images/Magazines/Issue_12025.pdf",
    },
    {
        "fingerprint": "strategy-field-response-workspace",
        "category": "field_operations", "priority": "medium",
        "title": "Build an offline-capable field response workspace",
        "summary": "Give authorised responders navigation, arrival confirmation, offline notes, evidence capture, safety check-ins and supervisor reassignment from a low-data mobile interface.",
        "source_label": "Government of Botswana police response standard",
        "source_url": "https://gov.bw/policing/reporting-incident-police",
    },
    {
        "fingerprint": "strategy-setswana-english-access",
        "category": "accessibility", "priority": "medium",
        "title": "Provide complete Setswana and English service journeys",
        "summary": "Translate intake, status updates, safety guidance and virtual assistance, with voice-note support and human review for sensitive or uncertain translations.",
        "source_label": "SmartBots public-sector transformation",
        "source_url": "https://smartbots.gov.bw/node/77",
    },
    {
        "fingerprint": "strategy-data-governance-controls",
        "category": "governance", "priority": "high",
        "title": "Approve retention, evidence access and resident appeal rules",
        "summary": "Define purpose-specific retention, deletion holds, access review, breach response, resident correction and appeal processes before live authority evidence is collected.",
        "source_label": "Botswana Data Protection Act implementation guidance",
        "source_url": "https://dailynews.gov.bw/common_up/dailynews/dailynews_pdf/18-11-2025_07-26-44_1763443604_dailynews_pdf.pdf",
    },
    {
        "fingerprint": "strategy-public-outcome-scorecard",
        "category": "performance", "priority": "medium",
        "title": "Measure service outcomes by city, town and ward",
        "summary": "Track acknowledgement, dispatch, arrival, resolution, reopened cases, handoffs, repeat hotspots and resident satisfaction, publishing only privacy-safe aggregates.",
        "source_label": "Botswana Police Service 2024 Annual Report",
        "source_url": "https://www.police.gov.bw/images/publications/Annual_Report_final2024.pdf",
    },
)


def refresh_operational_recommendations(now=None):
    now = now or timezone.now()
    for item in STRATEGIC_RECOMMENDATIONS:
        OperationalRecommendation.objects.update_or_create(
            fingerprint=item["fingerprint"],
            defaults={**item, "last_generated_at": now},
        )
    open_cases = DeliveryCase.objects.exclude(stage__in={"resolved", "closed"})
    unassigned = open_cases.filter(organisation__isnull=True).count()
    if unassigned:
        OperationalRecommendation.objects.update_or_create(
            fingerprint="engine-unassigned-routing",
            defaults={
                "category": "routing", "priority": "high",
                "title": "Close gaps in the central routing table",
                "summary": f"{unassigned} open case(s) have no responsible organisation. Add or correct routing policies before expanding intake.",
                "evidence": {"unassigned_cases": unassigned}, "last_generated_at": now,
            },
        )
    overdue = open_cases.filter(
        Q(acknowledged_at__isnull=True, acknowledgement_due_at__lt=now)
        | Q(assigned_to__isnull=True, assignment_due_at__lt=now)
        | Q(resolution_due_at__lt=now)
    ).values("organisation__name", "organisation_id").annotate(total=Count("id"))
    for row in overdue:
        org_name = row["organisation__name"] or "Central routing"
        OperationalRecommendation.objects.update_or_create(
            fingerprint=f"engine-sla-capacity-{row['organisation_id'] or 'central'}",
            defaults={
                "category": "capacity", "priority": "high" if row["total"] >= 3 else "medium",
                "title": f"Review response capacity for {org_name}",
                "summary": f"{row['total']} open case(s) have passed at least one delivery deadline. Review shift coverage, ownership and escalation routing.",
                "evidence": {"overdue_cases": row["total"]}, "last_generated_at": now,
            },
        )
    pending_groups = NeighborhoodWatchGroup.objects.filter(status="pending").count()
    if pending_groups:
        OperationalRecommendation.objects.update_or_create(
            fingerprint="engine-watch-review-backlog",
            defaults={
                "category": "community_policing", "priority": "medium",
                "title": "Clear the Neighborhood Watch review backlog",
                "summary": f"{pending_groups} proposed group(s) await police review. Assign a community-policing reviewer and publish a review deadline.",
                "evidence": {"pending_groups": pending_groups}, "last_generated_at": now,
            },
        )
    return OperationalRecommendation.objects.exclude(status=OperationalRecommendation.Status.DISMISSED)
