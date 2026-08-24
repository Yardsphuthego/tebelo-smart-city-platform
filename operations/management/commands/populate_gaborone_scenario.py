from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import AuditEvent
from operations.models import (
    Alert,
    AuthorityHandoff,
    AuthorityNotification,
    DeliveryCase,
    DeliveryEvent,
    DutyAssignment,
    DutyShift,
    Incident,
    IncidentCategory,
    IncidentEvent,
    Location,
    Membership,
    NeighborhoodWatchGroup,
    NeighborhoodWatchMembership,
    NotificationPreference,
    OperationalRecommendation,
    Organisation,
    ServiceDeskCase,
    ServiceMessage,
)


AREAS = (
    ("cbd", "Gaborone Central", "-24.654100", "25.908700"),
    ("broadhurst", "Broadhurst", "-24.628200", "25.923100"),
    ("block-8", "Block 8", "-24.602600", "25.925900"),
    ("phase-2", "Phase 2", "-24.655600", "25.883900"),
    ("g-west", "Gaborone West", "-24.668300", "25.889900"),
    ("old-naledi", "Old Naledi", "-24.682100", "25.912200"),
    ("kgale-view", "Kgale View", "-24.688800", "25.878600"),
)

PEOPLE = (
    ("resident.one@demo.tebelo.bw", "+26771000001", "Kago", "Molefe", "resident", False),
    ("resident.two@demo.tebelo.bw", "+26771000002", "Naledi", "Kgosidintsi", "resident", False),
    ("resident.three@demo.tebelo.bw", "+26771000003", "Thato", "Motsamai", "resident", False),
    ("police.dispatch@demo.tebelo.bw", "+26772000001", "Kefilwe", "Mooketsi", "officer", True),
    ("traffic.duty@demo.tebelo.bw", "+26772000002", "Olebile", "Sechele", "officer", True),
    ("council.desk@demo.tebelo.bw", "+26772000003", "Boitumelo", "Rantao", "officer", True),
    ("fire.duty@demo.tebelo.bw", "+26772000004", "Phenyo", "Mogapi", "officer", True),
    ("utilities.desk@demo.tebelo.bw", "+26772000005", "Lorato", "Modise", "officer", True),
    ("command.duty@demo.tebelo.bw", "+26772000006", "Tumisang", "Kebonang", "command", True),
)

MEMBERSHIPS = {
    "police.dispatch@demo.tebelo.bw": ("BPS-GAB", Membership.Role.DISPATCHER),
    "traffic.duty@demo.tebelo.bw": ("BPS-TRAFFIC", Membership.Role.RESPONDER),
    "council.desk@demo.tebelo.bw": ("GCC", Membership.Role.DISPATCHER),
    "fire.duty@demo.tebelo.bw": ("GCC-FIRE", Membership.Role.RESPONDER),
    "utilities.desk@demo.tebelo.bw": ("WUC", Membership.Role.DISPATCHER),
    "command.duty@demo.tebelo.bw": ("TEBELO-CMD", Membership.Role.SUPERVISOR),
}

INCIDENTS = (
    ("DEMO-GAB-001", "road-accident", "critical", "dispatched", "BPS-TRAFFIC", "traffic.duty@demo.tebelo.bw", "cbd", "-24.659500", "25.905600", "A1 near the Main Mall interchange", "Two-vehicle collision is affecting the northbound lane. Traffic officers have been dispatched.", 0, 32),
    ("DEMO-GAB-002", "water-problem", "high", "on_scene", "WUC", "utilities.desk@demo.tebelo.bw", "block-8", "-24.603400", "25.929100", "Block 8, near Segoditshane Way", "A burst water main is reducing pressure in nearby homes. A field team is isolating the damaged section.", 0, 74),
    ("DEMO-GAB-003", "broken-streetlight", "medium", "assigned", "GCC", "council.desk@demo.tebelo.bw", "broadhurst", "-24.625900", "25.921700", "Broadhurst, pedestrian crossing", "Street lighting is not working at a busy pedestrian crossing. Repair has been assigned.", 1, 18),
    ("DEMO-GAB-004", "suspicious-activity", "high", "verified", "BPS-GAB", "police.dispatch@demo.tebelo.bw", "phase-2", "-24.657300", "25.885600", "Phase 2 residential area", "Police have verified a community report and increased patrol attention in the area.", 1, 96),
    ("DEMO-GAB-005", "illegal-dumping", "medium", "triaged", "GCC", "council.desk@demo.tebelo.bw", "old-naledi", "-24.681300", "25.914100", "Old Naledi community grounds", "Waste dumped near community grounds has been recorded for council removal.", 2, 45),
    ("DEMO-GAB-006", "pothole", "low", "reported", "GCC", None, "g-west", "-24.669500", "25.892800", "Gaborone West, internal road", "A deep pothole is causing vehicles to move into the opposing lane.", 2, 210),
    ("DEMO-GAB-007", "traffic-light", "high", "resolved", "GCC", "council.desk@demo.tebelo.bw", "cbd", "-24.648900", "25.906300", "Nelson Mandela Drive intersection", "The traffic signal fault was repaired and normal sequencing has been restored.", 3, 80),
    ("DEMO-GAB-008", "electricity-problem", "medium", "resolved", "BPC", None, "kgale-view", "-24.689400", "25.880500", "Kgale View", "Electricity supply was restored after a local distribution fault.", 4, 125),
    ("DEMO-GAB-009", "fire", "critical", "closed", "GCC-FIRE", "fire.duty@demo.tebelo.bw", "g-west", "-24.674100", "25.883700", "Open land west of Phase 4", "A small veld fire was contained. Fire crews completed a safety inspection before closing the report.", 5, 65),
    ("DEMO-GAB-010", "blocked-road", "medium", "resolved", "GCC", "council.desk@demo.tebelo.bw", "broadhurst", "-24.631700", "25.927200", "Broadhurst access road", "A fallen tree was removed and the access road reopened.", 6, 110),
    ("DEMO-GAB-011", "dangerous-driving", "high", "assigned", "BPS-TRAFFIC", "traffic.duty@demo.tebelo.bw", "cbd", "-24.651800", "25.913900", "Independence Avenue", "Multiple residents reported dangerous driving. Traffic patrol has been assigned.", 0, 12),
    ("DEMO-GAB-012", "community-concern", "low", "verified", "GCC", "council.desk@demo.tebelo.bw", "phase-2", "-24.653900", "25.881500", "Phase 2 public space", "Damaged seating and litter at a public space have been verified for maintenance.", 3, 20),
)

SERVICES = (
    ("DEMO-VP-001", "police", "police_follow_up", "in_progress", "BPS-GAB", "police.dispatch@demo.tebelo.bw", "resident.one@demo.tebelo.bw", "Follow up on neighbourhood report", "Phase 2", "remote", "tn", "message", 0, 140),
    ("DEMO-GV-001", "government", "service_referral", "routed", "MCI-DTCO", None, "resident.two@demo.tebelo.bw", "Where to submit a trading licence query", "Gaborone West", "digital", "en", "sms", 1, 75),
    ("DEMO-TP-001", "traffic", "traffic_assistance", "waiting_resident", "BPS-TRAFFIC", "traffic.duty@demo.tebelo.bw", "resident.three@demo.tebelo.bw", "Clarification on accident report documents", "Gaborone Central", "digital", "en", "phone", 2, 90),
    ("DEMO-FE-001", "fire", "fire_safety", "resolved", "GCC-FIRE", "fire.duty@demo.tebelo.bw", "resident.one@demo.tebelo.bw", "Home fire-safety guidance", "Broadhurst", "mobility", "tn", "phone", 4, 160),
)


class Command(BaseCommand):
    help = "Idempotently populate a realistic synthetic Gaborone operations scenario."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="TebeloDemo!2026",
            help="Password assigned only when a scenario user is first created.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("configure_gaborone_authorities", verbosity=0)
        now = timezone.now()
        password = options["password"]
        city = Location.objects.get(code="gab", kind=Location.Kind.CITY)
        areas = self._areas(city)
        organisations = {item.short_name: item for item in Organisation.objects.all()}
        users, created_users = self._users(password)
        self._memberships_and_shifts(users, organisations, now)
        watches = self._watch_groups(users, organisations, areas, now)
        incidents = self._incidents(users, organisations, areas, watches, now)
        services = self._service_cases(users, organisations, now)
        self._alerts(users, areas, incidents, now)
        self._recommendations(now)
        self._handoffs_and_notifications(users, organisations, incidents, now)
        self._audit_activity(users, incidents, now)

        self.stdout.write(self.style.SUCCESS(
            "Scenario ready: "
            f"{len(areas)} areas, {len(watches)} watch groups, {len(incidents)} incidents, "
            f"{len(services)} virtual-service cases, {Alert.objects.filter(title__startswith='Gaborone').count()} alerts."
        ))
        if created_users:
            self.stdout.write(f"Created {created_users} scenario accounts. Initial password: {password}")
        else:
            self.stdout.write("Scenario accounts already existed; their passwords were not changed.")

    def _areas(self, city):
        areas = {}
        for code, name, latitude, longitude in AREAS:
            area, _ = Location.objects.update_or_create(
                parent=city,
                code=code,
                defaults={
                    "name": name,
                    "kind": Location.Kind.AREA,
                    "centre_latitude": latitude,
                    "centre_longitude": longitude,
                    "is_active": True,
                },
            )
            areas[code] = area
        return areas

    def _users(self, password):
        User = get_user_model()
        users = {}
        created_count = 0
        for email, phone, first_name, last_name, role, is_staff in PEOPLE:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "phone_number": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": role,
                    "is_staff": is_staff,
                    "is_active": True,
                    "is_verified": True,
                    "location_consent": True,
                },
            )
            if created:
                user.set_password(password)
                user.save(update_fields=("password",))
                created_count += 1
            else:
                User.objects.filter(pk=user.pk).update(
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    is_staff=is_staff,
                    is_active=True,
                    is_verified=True,
                )
                user.refresh_from_db()
            NotificationPreference.objects.get_or_create(user=user)
            users[email] = user
        return users, created_count

    def _memberships_and_shifts(self, users, organisations, now):
        for email, (short_name, role) in MEMBERSHIPS.items():
            organisation = organisations[short_name]
            user = users[email]
            Membership.objects.update_or_create(
                user=user,
                organisation=organisation,
                defaults={"role": role, "is_active": True},
            )
            shift, _ = DutyShift.objects.update_or_create(
                organisation=organisation,
                name="Gaborone live scenario duty",
                defaults={
                    "starts_at": now - timedelta(hours=4),
                    "ends_at": now + timedelta(hours=8),
                    "is_active": True,
                },
            )
            assignment_role = (
                DutyAssignment.Role.SUPERVISOR
                if role == Membership.Role.SUPERVISOR
                else DutyAssignment.Role.PRIMARY
            )
            DutyAssignment.objects.update_or_create(
                shift=shift,
                user=user,
                defaults={"role": assignment_role, "is_available": True},
            )

    def _watch_groups(self, users, organisations, areas, now):
        specifications = (
            ("DEMO-NW-001", "Phase 2 Neighbourhood Watch", "phase-2", "Community-led safety observations coordinated with Gaborone Police.", "resident.one@demo.tebelo.bw", "active", True, "1.8"),
            ("DEMO-NW-002", "Broadhurst Community Watch", "broadhurst", "Residents sharing verified safety concerns and prevention updates.", "resident.two@demo.tebelo.bw", "active", True, "2.2"),
            ("DEMO-NW-003", "Block 8 Safety Network", "block-8", "A new resident group awaiting police onboarding and verification.", "resident.three@demo.tebelo.bw", "pending", False, "1.4"),
        )
        groups = {}
        reviewer = users["police.dispatch@demo.tebelo.bw"]
        for reference, name, area_code, description, owner_email, status, visible, radius in specifications:
            area = areas[area_code]
            group, _ = NeighborhoodWatchGroup.objects.update_or_create(
                reference=reference,
                defaults={
                    "name": name,
                    "area": area,
                    "description": description,
                    "centre_latitude": area.centre_latitude,
                    "centre_longitude": area.centre_longitude,
                    "radius_km": radius,
                    "created_by": users[owner_email],
                    "police_organisation": organisations["BPS-GAB"],
                    "status": status,
                    "is_map_visible": visible,
                },
            )
            NeighborhoodWatchMembership.objects.update_or_create(
                group=group,
                user=users[owner_email],
                defaults={
                    "role": NeighborhoodWatchMembership.Role.COORDINATOR,
                    "status": NeighborhoodWatchMembership.Status.ACTIVE,
                    "reviewed_by": reviewer,
                    "reviewed_at": now - timedelta(days=2),
                },
            )
            groups[reference] = group
        NeighborhoodWatchMembership.objects.update_or_create(
            group=groups["DEMO-NW-001"],
            user=users["resident.two@demo.tebelo.bw"],
            defaults={
                "role": NeighborhoodWatchMembership.Role.MEMBER,
                "status": NeighborhoodWatchMembership.Status.ACTIVE,
                "reviewed_by": reviewer,
                "reviewed_at": now - timedelta(days=1),
            },
        )
        return groups

    def _incidents(self, users, organisations, areas, watches, now):
        reporter_cycle = (
            users["resident.one@demo.tebelo.bw"],
            users["resident.two@demo.tebelo.bw"],
            users["resident.three@demo.tebelo.bw"],
        )
        seeded = {}
        for index, item in enumerate(INCIDENTS):
            (reference, category_slug, priority, status, org_code, assignee_email, area_code,
             latitude, longitude, address, summary, days_ago, minutes_ago) = item
            created_at = now - timedelta(days=days_ago, minutes=minutes_ago)
            resolved = status in {Incident.Status.RESOLVED, Incident.Status.CLOSED}
            incident, _ = Incident.objects.update_or_create(
                reference=reference,
                defaults={
                    "category": IncidentCategory.objects.get(slug=category_slug),
                    "description": f"Synthetic operating scenario: {summary}",
                    "public_summary": summary,
                    "reporter": reporter_cycle[index % len(reporter_cycle)],
                    "anonymous": index == 5,
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": address,
                    "location": areas[area_code],
                    "occurred_at": created_at - timedelta(minutes=10),
                    "status": status,
                    "priority": priority,
                    "assigned_organisation": organisations[org_code],
                    "assigned_to": users.get(assignee_email),
                    "is_public": status not in {Incident.Status.REPORTED, Incident.Status.REJECTED},
                    "verified_at": created_at + timedelta(minutes=12) if status != Incident.Status.REPORTED else None,
                    "resolved_at": created_at + timedelta(hours=3) if resolved else None,
                    "watch_group": watches["DEMO-NW-001"] if reference in {"DEMO-GAB-004", "DEMO-GAB-012"} else None,
                },
            )
            Incident.objects.filter(pk=incident.pk).update(created_at=created_at, updated_at=now)
            self._incident_timeline(incident, users, status, created_at)
            self._shape_delivery_case(
                incident.delivery_case,
                status,
                created_at,
                now,
                users["command.duty@demo.tebelo.bw"],
            )
            seeded[reference] = incident
        return seeded

    def _incident_timeline(self, incident, users, status, created_at):
        actor = users["command.duty@demo.tebelo.bw"]
        events = [("reported", "", Incident.Status.REPORTED, "Report received from the public channel.", 0)]
        if status != Incident.Status.REPORTED:
            events.append(("verified", Incident.Status.REPORTED, Incident.Status.VERIFIED, "Location and public details verified.", 12))
        if status in {Incident.Status.ASSIGNED, Incident.Status.DISPATCHED, Incident.Status.ON_SCENE, Incident.Status.RESOLVED, Incident.Status.CLOSED}:
            events.append(("assigned", Incident.Status.VERIFIED, Incident.Status.ASSIGNED, "Owning authority and duty officer assigned.", 24))
        if status in {Incident.Status.DISPATCHED, Incident.Status.ON_SCENE, Incident.Status.RESOLVED, Incident.Status.CLOSED}:
            events.append(("response", Incident.Status.ASSIGNED, Incident.Status.DISPATCHED, "Response team dispatched through the command queue.", 38))
        if status in {Incident.Status.RESOLVED, Incident.Status.CLOSED}:
            events.append(("resolved", Incident.Status.DISPATCHED, Incident.Status.RESOLVED, "Authority confirmed that the service action was completed.", 180))
        for event_type, from_status, to_status, note, minutes in events:
            event, _ = IncidentEvent.objects.get_or_create(
                incident=incident,
                event_type=event_type,
                note=note,
                defaults={"actor": actor, "from_status": from_status, "to_status": to_status},
            )
            IncidentEvent.objects.filter(pk=event.pk).update(created_at=created_at + timedelta(minutes=minutes))

    def _shape_delivery_case(self, case, source_status, created_at, now, actor):
        if source_status in {Incident.Status.RESOLVED, Incident.Status.CLOSED}:
            stage = DeliveryCase.Stage.RESOLVED if source_status == Incident.Status.RESOLVED else DeliveryCase.Stage.CLOSED
        elif source_status in {Incident.Status.DISPATCHED, Incident.Status.ON_SCENE}:
            stage = DeliveryCase.Stage.IN_PROGRESS
        elif source_status == Incident.Status.ASSIGNED:
            stage = DeliveryCase.Stage.ASSIGNED
        elif source_status in {Incident.Status.VERIFIED, Incident.Status.TRIAGED}:
            stage = DeliveryCase.Stage.ACKNOWLEDGED
        else:
            stage = DeliveryCase.Stage.OPEN
        overdue = case.incident.reference in {"DEMO-GAB-004", "DEMO-GAB-005", "DEMO-GAB-006"}
        DeliveryCase.objects.filter(pk=case.pk).update(
            stage=stage,
            acknowledgement_due_at=now - timedelta(minutes=25) if overdue else created_at + timedelta(minutes=30),
            assignment_due_at=now - timedelta(minutes=10) if overdue else created_at + timedelta(hours=1),
            resolution_due_at=created_at + timedelta(hours=24),
            acknowledged_at=created_at + timedelta(minutes=12) if stage != DeliveryCase.Stage.OPEN else None,
            assigned_at=created_at + timedelta(minutes=24) if stage in {DeliveryCase.Stage.ASSIGNED, DeliveryCase.Stage.IN_PROGRESS, DeliveryCase.Stage.RESOLVED, DeliveryCase.Stage.CLOSED} else None,
            resolved_at=created_at + timedelta(hours=3) if stage in {DeliveryCase.Stage.RESOLVED, DeliveryCase.Stage.CLOSED} else None,
            escalation_level=1 if overdue else 0,
            last_breach="assignment" if overdue else "",
            created_at=created_at,
            updated_at=now,
        )
        case.refresh_from_db()
        event, _ = DeliveryEvent.objects.get_or_create(
            case=case,
            event_type="scenario_status",
            defaults={
                "actor": actor,
                "organisation": case.organisation,
                "note": "Scenario timeline prepared for dashboard review.",
                "metadata": {"stage": stage},
            },
        )
        DeliveryEvent.objects.filter(pk=event.pk).update(created_at=created_at + timedelta(minutes=25))

    def _service_cases(self, users, organisations, now):
        seeded = {}
        for item in SERVICES:
            (reference, desk, request_type, status, org_code, assignee_email, resident_email,
             subject, location, access, language, contact, days_ago, minutes_ago) = item
            created_at = now - timedelta(days=days_ago, minutes=minutes_ago)
            service, _ = ServiceDeskCase.objects.update_or_create(
                reference=reference,
                defaults={
                    "resident": users[resident_email],
                    "desk": desk,
                    "request_type": request_type,
                    "status": status,
                    "subject": subject,
                    "access_context": access,
                    "location_description": location,
                    "preferred_language": language,
                    "preferred_contact": contact,
                    "assigned_organisation": organisations[org_code],
                    "assigned_to": users.get(assignee_email),
                    "is_closed": status == ServiceDeskCase.Status.CLOSED,
                },
            )
            ServiceDeskCase.objects.filter(pk=service.pk).update(created_at=created_at, updated_at=now)
            resident = users[resident_email]
            message, _ = ServiceMessage.objects.get_or_create(
                case=service,
                sender=resident,
                body=f"Please assist with this request: {subject.lower()}.",
            )
            ServiceMessage.objects.filter(pk=message.pk).update(created_at=created_at + timedelta(minutes=2))
            if assignee_email:
                reply, _ = ServiceMessage.objects.get_or_create(
                    case=service,
                    sender=users[assignee_email],
                    body="Your request has been received and is being handled through the accountable service queue.",
                )
                ServiceMessage.objects.filter(pk=reply.pk).update(created_at=created_at + timedelta(minutes=28))
            case = service.delivery_case
            delivery_stage = {
                ServiceDeskCase.Status.SUBMITTED: DeliveryCase.Stage.OPEN,
                ServiceDeskCase.Status.ROUTED: DeliveryCase.Stage.ACKNOWLEDGED,
                ServiceDeskCase.Status.IN_PROGRESS: DeliveryCase.Stage.IN_PROGRESS,
                ServiceDeskCase.Status.WAITING_RESIDENT: DeliveryCase.Stage.IN_PROGRESS,
                ServiceDeskCase.Status.RESOLVED: DeliveryCase.Stage.RESOLVED,
                ServiceDeskCase.Status.CLOSED: DeliveryCase.Stage.CLOSED,
            }[status]
            overdue = reference == "DEMO-GV-001"
            DeliveryCase.objects.filter(pk=case.pk).update(
                stage=delivery_stage,
                acknowledgement_due_at=now - timedelta(minutes=30) if overdue else created_at + timedelta(hours=1),
                assignment_due_at=now - timedelta(minutes=5) if overdue else created_at + timedelta(hours=4),
                resolution_due_at=created_at + timedelta(days=2),
                acknowledged_at=created_at + timedelta(minutes=28) if status != ServiceDeskCase.Status.SUBMITTED else None,
                assigned_at=created_at + timedelta(minutes=40) if assignee_email else None,
                resolved_at=created_at + timedelta(hours=2) if status == ServiceDeskCase.Status.RESOLVED else None,
                escalation_level=1 if overdue else 0,
                last_breach="assignment" if overdue else "",
                created_at=created_at,
                updated_at=now,
            )
            seeded[reference] = service
        return seeded

    def _alerts(self, users, areas, incidents, now):
        publisher = users["command.duty@demo.tebelo.bw"]
        alerts = (
            ("Gaborone traffic advisory — A1", "Expect delays near the Main Mall interchange while officers clear a collision.", "traffic", "high", "radius", "cbd", "DEMO-GAB-001", 6),
            ("Gaborone water service update — Block 8", "A repair team is attending a burst main. Some properties may experience reduced pressure.", "utilities", "medium", "location", "block-8", "DEMO-GAB-002", 10),
            ("Gaborone community safety notice — Phase 2", "Verified patrol activity is under way. Residents should use official reporting channels for observations.", "safety", "medium", "radius", "phase-2", "DEMO-GAB-004", 12),
        )
        for title, summary, category, severity, scope, area_code, incident_ref, hours in alerts:
            area = areas[area_code]
            Alert.objects.update_or_create(
                title=title,
                defaults={
                    "summary": summary,
                    "category": category,
                    "severity": severity,
                    "scope": scope,
                    "location": area,
                    "latitude": area.centre_latitude,
                    "longitude": area.centre_longitude,
                    "radius_km": "3.00",
                    "source_incident": incidents[incident_ref],
                    "published_by": publisher,
                    "starts_at": now - timedelta(minutes=20),
                    "ends_at": now + timedelta(hours=hours),
                    "is_published": True,
                },
            )

    def _recommendations(self, now):
        recommendations = (
            ("scenario:coverage:phase2", "coverage", "high", "Extend evening patrol coverage in Phase 2", "Recent verified reports and neighbourhood-watch activity indicate demand for a visible evening coverage window.", {"verified_reports": 2, "watch_groups": 1}),
            ("scenario:water:block8", "infrastructure", "medium", "Review recurring Block 8 water response readiness", "Use repair times and resident updates to identify isolation points that need faster field access.", {"active_water_cases": 1}),
            ("scenario:traffic:cbd", "mobility", "high", "Coordinate peak-hour traffic incident staging", "Define pre-agreed staging points for traffic officers and medical response near high-volume CBD junctions.", {"critical_incidents": 1}),
        )
        for fingerprint, category, priority, title, summary, evidence in recommendations:
            OperationalRecommendation.objects.update_or_create(
                fingerprint=fingerprint,
                defaults={
                    "category": category,
                    "priority": priority,
                    "title": title,
                    "summary": summary,
                    "evidence": evidence,
                    "source_label": "TEBELO synthetic operating scenario",
                    "source_url": "",
                    "status": OperationalRecommendation.Status.PROPOSED,
                    "last_generated_at": now,
                },
            )

    def _handoffs_and_notifications(self, users, organisations, incidents, now):
        case = incidents["DEMO-GAB-006"].delivery_case
        AuthorityHandoff.objects.update_or_create(
            case=case,
            to_organisation=organisations["GCC"],
            status=AuthorityHandoff.Status.REQUESTED,
            defaults={
                "from_organisation": organisations["TEBELO-CMD"],
                "requested_by": users["command.duty@demo.tebelo.bw"],
                "reason": "Road-surface repair requires confirmed council ownership and scheduling.",
            },
        )
        notification_specs = (
            ("command.duty@demo.tebelo.bw", incidents["DEMO-GAB-004"].delivery_case, "sla_breach", "Assignment deadline exceeded", "Phase 2 safety report requires an updated ownership decision."),
            ("council.desk@demo.tebelo.bw", case, "handoff", "Authority handoff awaiting response", "Accept or decline ownership of the Gaborone West road repair case."),
        )
        for email, delivery, kind, title, body in notification_specs:
            AuthorityNotification.objects.update_or_create(
                user=users[email],
                delivery_case=delivery,
                title=title,
                defaults={"kind": kind, "body": body, "read_at": None},
            )

    def _audit_activity(self, users, incidents, now):
        events = (
            ("scenario.incident.verified", "DEMO-GAB-004"),
            ("scenario.alert.published", "DEMO-GAB-001"),
            ("scenario.handoff.requested", "DEMO-GAB-006"),
        )
        actor = users["command.duty@demo.tebelo.bw"]
        for action, reference in events:
            incident = incidents[reference]
            AuditEvent.objects.update_or_create(
                action=action,
                object_type=incident._meta.label,
                object_id=str(incident.pk),
                defaults={
                    "actor": actor,
                    "metadata": {"scenario": True, "reference": reference},
                    "ip_address": "127.0.0.1",
                },
            )
