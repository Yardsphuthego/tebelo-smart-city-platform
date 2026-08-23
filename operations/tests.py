from datetime import timedelta
from io import StringIO

from django.contrib import admin
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from core.models import AuditEvent
from .delivery import (
    process_due_delivery_cases,
    refresh_operational_recommendations,
    request_handoff,
    respond_handoff,
)
from .models import (
    AuthorityHandoff,
    AuthorityNotification,
    DeliveryCase,
    DutyAssignment,
    DutyShift,
    Incident,
    IncidentCategory,
    IncidentEvent,
    Location,
    Membership,
    NeighborhoodWatchGroup,
    NeighborhoodWatchMembership,
    OperationalRecommendation,
    Organisation,
    ServiceDeskCase,
    ServiceRoutingPolicy,
)


class IncidentWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = Location.objects.get(code="gab")
        cls.category = IncidentCategory.objects.get(slug="road-accident")
        cls.org = Organisation.objects.create(name="Gaborone Traffic Police", short_name="GTP", kind="traffic", location=cls.city)
        cls.resident = User.objects.create_user(email="resident@example.com", password="Very-secure-pass-123")
        cls.officer = User.objects.create_user(email="officer@example.com", password="Very-secure-pass-123", role="officer")
        Membership.objects.create(user=cls.officer, organisation=cls.org, role="dispatcher")

    def test_report_is_routed_and_audited(self):
        self.client.force_login(self.resident)
        response = self.client.post(reverse("report_incident"), {
            "category": self.category.pk, "description": "Two cars collided at the junction.",
            "latitude": "-24.628208", "longitude": "25.923147", "anonymous": "on", "location_permission": "on",
        })
        self.assertEqual(response.status_code, 302)
        incident = Incident.objects.get()
        self.assertEqual(incident.assigned_organisation, self.org)
        self.assertEqual(incident.priority, "high")
        self.assertTrue(incident.reference.startswith("BW-"))
        self.assertTrue(IncidentEvent.objects.filter(incident=incident, event_type="reported").exists())
        self.assertTrue(AuditEvent.objects.filter(action="incident.created", object_id=str(incident.pk)).exists())

    def test_private_incident_cannot_be_viewed_by_stranger(self):
        incident = Incident.objects.create(category=self.category, reporter=self.resident, description="Private report", latitude=-24.62, longitude=25.92)
        stranger = User.objects.create_user(email="stranger@example.com", password="Very-secure-pass-123")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("incident_detail", args=[incident.pk])).status_code, 403)

    def test_unrelated_officer_cannot_manage_incident(self):
        incident = Incident.objects.create(category=self.category, reporter=self.resident, description="Test incident", latitude=-24.62, longitude=25.92, assigned_organisation=self.org)
        other_org = Organisation.objects.create(name="Other Police", short_name="OP", kind="police", location=self.city)
        stranger = User.objects.create_user(email="other@example.com", password="Very-secure-pass-123", role="officer")
        Membership.objects.create(user=stranger, organisation=other_org, role="dispatcher")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse("manage_incident", args=[incident.pk])).status_code, 404)

    def test_public_geojson_redacts_description_and_reporter(self):
        Incident.objects.create(category=self.category, reporter=self.resident, description="Sensitive identifying details", public_summary="Road collision reported.", latitude=-24.62, longitude=25.92, is_public=True)
        payload = self.client.get(reverse("public_incidents_geojson")).json()
        rendered = str(payload)
        self.assertNotIn("Sensitive identifying details", rendered)
        self.assertNotIn("resident@example.com", rendered)
        self.assertIn("Road collision reported", rendered)

    def test_government_virtual_assistance_case_is_referenced_and_audited(self):
        self.client.force_login(self.resident)
        response = self.client.post(reverse("service_desks"), {
            "desk": "government",
            "request_type": "service_referral",
            "subject": "Help locating the correct licensing office",
            "access_context": "remote",
            "location_description": "Near Tlokweng border area",
            "preferred_language": "tn",
            "preferred_contact": "message",
            "incident": "",
            "message": "Please guide me to the correct government service.",
            "non_emergency_acknowledgement": "on",
        })
        self.assertEqual(response.status_code, 302)
        case = ServiceDeskCase.objects.get()
        self.assertTrue(case.reference.startswith("GV-"))
        self.assertEqual(case.status, ServiceDeskCase.Status.SUBMITTED)
        self.assertTrue(AuditEvent.objects.filter(
            action="service_case.created", object_id=str(case.pk)
        ).exists())

    def test_virtual_service_rejects_request_type_for_wrong_desk(self):
        self.client.force_login(self.resident)
        response = self.client.post(reverse("service_desks"), {
            "desk": "police",
            "request_type": "application_guidance",
            "subject": "Mismatched request",
            "access_context": "digital",
            "preferred_language": "en",
            "preferred_contact": "message",
            "incident": "",
            "message": "This request should not be accepted by this desk.",
            "non_emergency_acknowledgement": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a request type that belongs")
        self.assertFalse(ServiceDeskCase.objects.exists())


class NeighborhoodWatchWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = Location.objects.get(code="gab")
        cls.category = IncidentCategory.objects.get(slug="road-accident")
        cls.police = Organisation.objects.create(
            name="Gaborone Police Service", short_name="GPS", kind="police", location=cls.city
        )
        cls.resident = User.objects.create_user(
            phone_number="+26771110001", password="Very-secure-pass-123"
        )
        cls.officer = User.objects.create_user(
            email="watch.officer@example.com", password="Very-secure-pass-123", role="officer"
        )
        Membership.objects.create(
            user=cls.officer, organisation=cls.police, role=Membership.Role.SUPERVISOR
        )

    def create_group(self, status=NeighborhoodWatchGroup.Status.PENDING):
        group = NeighborhoodWatchGroup.objects.create(
            name="Block 8 Community Watch",
            area=self.city,
            description="Residents coordinating verified community safety reporting.",
            centre_latitude="-24.604200",
            centre_longitude="25.930100",
            radius_km="1.5",
            created_by=self.resident,
            police_organisation=self.police,
            status=status,
            is_map_visible=status == NeighborhoodWatchGroup.Status.ACTIVE,
        )
        NeighborhoodWatchMembership.objects.create(
            group=group,
            user=self.resident,
            role=NeighborhoodWatchMembership.Role.COORDINATOR,
            status=(
                NeighborhoodWatchMembership.Status.ACTIVE
                if status == NeighborhoodWatchGroup.Status.ACTIVE
                else NeighborhoodWatchMembership.Status.PENDING
            ),
        )
        return group

    def test_resident_proposal_stays_private_until_police_approval(self):
        self.client.force_login(self.resident)
        response = self.client.post(reverse("watch_group_create"), {
            "name": "Tsholofelo East Watch",
            "area": self.city.pk,
            "description": "A structured resident safety group for the area.",
            "centre_latitude": "-24.620000",
            "centre_longitude": "25.920000",
            "radius_km": "1.2",
            "police_review_acknowledgement": "on",
        })
        self.assertEqual(response.status_code, 302)
        group = NeighborhoodWatchGroup.objects.get(name="Tsholofelo East Watch")
        self.assertEqual(group.status, NeighborhoodWatchGroup.Status.PENDING)
        self.assertFalse(group.is_map_visible)
        self.assertEqual(self.client.get(reverse("public_watch_groups_geojson")).json()["features"], [])
        self.assertTrue(AuditEvent.objects.filter(action="watch_group.created", object_id=str(group.pk)).exists())

    def test_police_can_approve_group_and_membership(self):
        group = self.create_group()
        self.client.force_login(self.officer)
        response = self.client.post(reverse("watch_group_action", args=[group.pk]), {"action": "approve"})
        self.assertRedirects(response, reverse("watch_command"))
        group.refresh_from_db()
        coordinator = group.memberships.get(user=self.resident)
        self.assertEqual(group.status, NeighborhoodWatchGroup.Status.ACTIVE)
        self.assertTrue(group.is_map_visible)
        self.assertEqual(coordinator.status, NeighborhoodWatchMembership.Status.ACTIVE)

    def test_public_map_exposes_coverage_not_member_identity(self):
        group = self.create_group(NeighborhoodWatchGroup.Status.ACTIVE)
        payload = self.client.get(reverse("public_watch_groups_geojson")).json()
        rendered = str(payload)
        self.assertIn(group.name, rendered)
        self.assertIn("member_count", rendered)
        self.assertEqual(
            {feature["geometry"]["type"] for feature in payload["features"]},
            {"Point", "Polygon"},
        )
        self.assertNotIn(self.resident.phone_number, rendered)
        self.assertNotIn("created_by", rendered)

    def test_active_member_report_routes_to_supervising_police(self):
        group = self.create_group(NeighborhoodWatchGroup.Status.ACTIVE)
        self.client.force_login(self.resident)
        response = self.client.post(reverse("report_incident"), {
            "watch_group": group.pk,
            "category": self.category.pk,
            "description": "Unsafe driving repeatedly observed near the community route.",
            "latitude": "-24.604200",
            "longitude": "25.930100",
            "location_permission": "on",
        })
        self.assertEqual(response.status_code, 302)
        incident = Incident.objects.get()
        self.assertEqual(incident.watch_group, group)
        self.assertEqual(incident.assigned_organisation, self.police)

    def test_non_member_cannot_report_as_a_watch_group(self):
        group = self.create_group(NeighborhoodWatchGroup.Status.ACTIVE)
        stranger = User.objects.create_user(
            phone_number="+26771110002", password="Very-secure-pass-123"
        )
        self.client.force_login(stranger)
        response = self.client.post(reverse("report_incident"), {
            "watch_group": group.pk,
            "category": self.category.pk,
            "description": "Attempt to report through a group without membership.",
            "latitude": "-24.604200",
            "longitude": "25.930100",
            "location_permission": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Incident.objects.exists())


class ServiceDeliveryEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = Location.objects.get(code="gab")
        cls.category = IncidentCategory.objects.get(slug="road-accident")
        cls.primary_org = Organisation.objects.create(
            name="Engine Traffic Operations", short_name="ETO", kind="traffic", location=cls.city
        )
        cls.receiving_org = Organisation.objects.create(
            name="Engine Police Operations", short_name="EPO", kind="police", location=cls.city
        )
        cls.resident = User.objects.create_user(
            phone_number="+26772220001", password="Very-secure-pass-123"
        )
        cls.officer = User.objects.create_user(
            email="engine.officer@example.com", password="Very-secure-pass-123", role="officer"
        )
        cls.receiver = User.objects.create_user(
            email="engine.receiver@example.com", password="Very-secure-pass-123", role="officer"
        )
        Membership.objects.create(
            user=cls.officer, organisation=cls.primary_org, role=Membership.Role.SUPERVISOR
        )
        Membership.objects.create(
            user=cls.receiver, organisation=cls.receiving_org, role=Membership.Role.SUPERVISOR
        )
        now = timezone.now()
        cls.shift = DutyShift.objects.create(
            organisation=cls.primary_org,
            name="Operational test shift",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=8),
        )
        DutyAssignment.objects.create(shift=cls.shift, user=cls.officer, role="primary")
        cls.policy = ServiceRoutingPolicy.objects.create(
            name="High-priority traffic dispatch",
            case_type=ServiceRoutingPolicy.CaseType.INCIDENT,
            incident_category=cls.category,
            incident_priority=Incident.Priority.HIGH,
            destination_organisation=cls.primary_org,
            escalation_organisation=cls.primary_org,
            acknowledgement_minutes=10,
            assignment_minutes=20,
            resolution_minutes=180,
        )

    def create_incident(self):
        return Incident.objects.create(
            category=self.category,
            reporter=self.resident,
            description="Engine workflow incident",
            latitude="-24.620000",
            longitude="25.920000",
            priority=Incident.Priority.HIGH,
        )

    def test_policy_and_active_shift_assign_new_incident(self):
        before = timezone.now()
        incident = self.create_incident()
        delivery = incident.delivery_case
        self.assertEqual(delivery.policy, self.policy)
        self.assertEqual(delivery.organisation, self.primary_org)
        self.assertEqual(delivery.assigned_to, self.officer)
        self.assertEqual(delivery.stage, DeliveryCase.Stage.ASSIGNED)
        self.assertGreater(delivery.acknowledgement_due_at, before)
        incident.refresh_from_db()
        self.assertEqual(incident.assigned_organisation, self.primary_org)
        self.assertEqual(incident.assigned_to, self.officer)
        self.assertTrue(AuthorityNotification.objects.filter(
            user=self.officer, kind=AuthorityNotification.Kind.ASSIGNMENT
        ).exists())

    def test_sla_escalation_is_idempotent_within_repeat_window(self):
        delivery = self.create_incident().delivery_case
        now = timezone.now()
        DeliveryCase.objects.filter(pk=delivery.pk).update(
            acknowledgement_due_at=now - timedelta(minutes=1)
        )
        self.assertEqual(process_due_delivery_cases(now), 1)
        self.assertEqual(process_due_delivery_cases(now), 0)
        delivery.refresh_from_db()
        self.assertEqual(delivery.escalation_level, 1)
        self.assertEqual(delivery.last_breach, "acknowledgement")
        self.assertTrue(delivery.events.filter(event_type="sla_escalated").exists())
        self.assertTrue(AuthorityNotification.objects.filter(
            user=self.officer, kind=AuthorityNotification.Kind.SLA_BREACH
        ).exists())

    def test_accepted_handoff_changes_engine_and_source_ownership(self):
        incident = self.create_incident()
        delivery = incident.delivery_case
        handoff = request_handoff(
            case=delivery,
            to_organisation=self.receiving_org,
            user=self.officer,
            reason="Police investigation is required.",
        )
        self.assertEqual(handoff.status, AuthorityHandoff.Status.REQUESTED)
        respond_handoff(handoff=handoff, user=self.receiver, accept=True)
        handoff.refresh_from_db()
        delivery.refresh_from_db()
        incident.refresh_from_db()
        self.assertEqual(handoff.status, AuthorityHandoff.Status.ACCEPTED)
        self.assertEqual(delivery.organisation, self.receiving_org)
        self.assertEqual(incident.assigned_organisation, self.receiving_org)

    def test_recommendations_include_national_priorities_and_engine_gaps(self):
        self.policy.is_active = False
        self.policy.save(update_fields=("is_active", "updated_at"))
        DutyAssignment.objects.filter(shift=self.shift).delete()
        Organisation.objects.filter(pk=self.primary_org.pk).update(is_active=False)
        incident = self.create_incident()
        self.assertIsNone(incident.delivery_case.organisation)
        recommendations = refresh_operational_recommendations()
        self.assertTrue(recommendations.filter(fingerprint="strategy-survivor-safe-gbv").exists())
        self.assertEqual(recommendations.filter(fingerprint__startswith="strategy-").count(), 11)
        city_services = recommendations.get(fingerprint="strategy-government-service-catalogue")
        self.assertIn("independent city and town service directory", city_services.title.lower())
        self.assertIn("TEBELO city and town operating platform", city_services.summary)
        self.assertNotIn("1Gov", city_services.summary)
        self.assertTrue(recommendations.filter(fingerprint="engine-unassigned-routing").exists())
        self.assertEqual(
            OperationalRecommendation.objects.get(fingerprint="engine-unassigned-routing").evidence["unassigned_cases"],
            1,
        )

    def test_resident_cannot_open_delivery_command(self):
        self.client.force_login(self.resident)
        self.assertEqual(self.client.get(reverse("delivery_command")).status_code, 403)


class GaboroneAuthorityConfigurationTests(TestCase):
    def test_configuration_is_complete_and_idempotent(self):
        administrator = User.objects.create_superuser(
            email="configuration-admin@example.com",
            password="Very-secure-pass-123",
        )
        output = StringIO()
        call_command("configure_gaborone_authorities", stdout=output)
        call_command("configure_gaborone_authorities", stdout=output)

        self.assertEqual(Organisation.objects.count(), 10)
        self.assertEqual(ServiceRoutingPolicy.objects.count(), 28)
        self.assertEqual(
            Organisation.objects.exclude(short_name="TEBELO-CMD").filter(
                integration_status=Organisation.IntegrationStatus.ONBOARDING
            ).count(),
            9,
        )
        command_centre = Organisation.objects.get(short_name="TEBELO-CMD")
        self.assertTrue(Membership.objects.filter(
            user=administrator,
            organisation=command_centre,
            role=Membership.Role.ADMIN,
            is_active=True,
        ).exists())
        self.assertEqual(DutyShift.objects.filter(organisation=command_centre).count(), 1)
        self.assertEqual(
            DutyAssignment.objects.filter(shift__organisation=command_centre, user=administrator).count(),
            1,
        )


class PageTests(TestCase):
    def test_public_pages_render(self):
        for name in ("home", "city_map", "alerts", "around_me", "emergency"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "public-header")
                self.assertContains(response, "css/interactions.css")
                self.assertContains(response, "css/palette.css")
                self.assertContains(response, "js/theme.js")
                self.assertContains(response, "js/loading.js")
                self.assertNotContains(response, "app-sidebar")

    def test_landing_and_authenticated_dashboard_are_separate(self):
        landing = self.client.get(reverse("home"))
        self.assertNotContains(landing, "Your digital connection to Gaborone")
        self.assertNotContains(landing, "Join with my phone number")
        self.assertNotContains(landing, "Gaborone today")
        self.assertContains(landing, "Aerial view of Gaborone")
        self.assertContains(landing, "city-information-strip")
        self.assertContains(landing, "Emergency")
        self.assertNotContains(landing, "data-tebelo-map")

        dashboard = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            dashboard,
            f"{reverse('login')}?next={reverse('dashboard')}",
        )

    def test_maps_use_shared_responsive_controller(self):
        resident = User.objects.create_user(
            email="dashboard@example.com", password="Very-secure-pass-123"
        )
        self.client.force_login(resident)
        for name in ("dashboard", "city_map"):
            response = self.client.get(reverse(name))
            self.assertContains(response, "data-tebelo-map")
            self.assertContains(response, "map-container is-loading")
            self.assertContains(response, "js/maps.js")
            self.assertContains(response, reverse("public_incidents_geojson"))
            self.assertContains(response, reverse("public_watch_groups_geojson"))

    def test_resident_workspace_uses_top_account_navigation(self):
        resident = User.objects.create_user(
            email="resident-navigation@example.com", password="Very-secure-pass-123"
        )
        self.client.force_login(resident)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "civic-top-strip")
        self.assertContains(response, "workspace-service-nav")
        self.assertContains(response, "workspace-account-menu")
        self.assertContains(response, "My reports")
        account_panel = response.content.decode().split('class="workspace-account-panel"', 1)[1].split("</details>", 1)[0]
        self.assertIn("Account settings", account_panel)
        self.assertIn("Appearance", account_panel)
        self.assertNotIn("My reports", account_panel)
        self.assertNotIn("Authority operations", account_panel)
        self.assertNotContains(response, "app-sidebar")

    def test_unfold_operations_dashboard_renders_for_staff(self):
        admin_user = User.objects.create_superuser(
            email="command@example.com", password="Very-secure-pass-123"
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gaborone Command")
        self.assertContains(response, "overview-page-heading")
        self.assertContains(response, "overview-subtitle-strip")
        self.assertContains(response, "Active incident queue")
        self.assertContains(response, "admin-civic-strip")
        self.assertContains(response, "admin-ticker-track")
        self.assertContains(response, "admin-platform-nav")
        self.assertContains(response, "admin-account-menu")
        self.assertContains(response, "admin-create-menu")
        self.assertContains(response, "Create new")
        self.assertContains(response, reverse("admin:operations_organisation_add"))
        self.assertContains(response, "css/palette.css")
        self.assertContains(response, 'class="is-active" aria-current="page">Overview</a>')
        account_panel = response.content.decode().split('class="admin-account-panel"', 1)[1].split("</details>", 1)[0]
        self.assertIn("Security settings", account_panel)
        self.assertNotIn("Service delivery", account_panel)
        self.assertNotIn("Incidents", account_panel)
        self.assertNotContains(response, 'id="nav-sidebar"')
        self.assertContains(response, "js/loading.js")
        self.assertIn("'unsafe-eval'", response.headers["Content-Security-Policy"])

        incidents = self.client.get(reverse("admin:operations_incident_changelist"))
        self.assertContains(incidents, 'class="is-active" aria-current="page">Incidents</a>')

    def test_super_admin_has_full_control_and_can_create_an_organisation(self):
        admin_user = User.objects.create_superuser(
            email="network-admin@example.com", password="Very-secure-pass-123"
        )
        request = RequestFactory().get(reverse("admin:index"))
        request.user = admin_user
        for model, model_admin in admin.site._registry.items():
            if model._meta.app_label not in {"accounts", "operations"}:
                continue
            with self.subTest(model=model._meta.label):
                self.assertTrue(model_admin.has_view_permission(request))
                self.assertTrue(model_admin.has_add_permission(request))
                self.assertTrue(model_admin.has_change_permission(request))
                self.assertTrue(model_admin.has_delete_permission(request))

        audit_admin = admin.site._registry[AuditEvent]
        self.assertTrue(audit_admin.has_view_permission(request))
        self.assertFalse(audit_admin.has_add_permission(request))
        self.assertFalse(audit_admin.has_change_permission(request))
        self.assertFalse(audit_admin.has_delete_permission(request))

        self.client.force_login(admin_user)
        add_page = self.client.get(reverse("admin:operations_organisation_add"))
        self.assertEqual(add_page.status_code, 200)
        self.assertContains(add_page, "Add organisation")

        location = Location.objects.get(code="gab")
        response = self.client.post(
            reverse("admin:operations_organisation_add"),
            {
                "name": "Gaborone Community Safety Office",
                "short_name": "GCSO",
                "kind": Organisation.Kind.GOVERNMENT,
                "location": location.pk,
                "emergency_phone": "+267 399 9999",
                "integration_status": Organisation.IntegrationStatus.CONFIGURED,
                "source_url": "https://example.gov.bw/safety",
                "is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Organisation.objects.filter(short_name="GCSO", is_active=True).exists())

        recommendation = self.client.post(
            reverse("admin:operations_operationalrecommendation_add"),
            {
                "category": "service_quality",
                "priority": OperationalRecommendation.Priority.MEDIUM,
                "title": "Extend weekend service coverage",
                "summary": "Measure demand and schedule accountable weekend coverage.",
                "source_label": "Command review",
                "source_url": "",
                "status": OperationalRecommendation.Status.PROPOSED,
                "_save": "Save",
            },
        )
        self.assertEqual(recommendation.status_code, 302)
        created = OperationalRecommendation.objects.get(title="Extend weekend service coverage")
        self.assertTrue(created.fingerprint.startswith("manual:"))

    def test_delivery_engine_and_case_use_native_super_admin_layout(self):
        admin_user = User.objects.create_superuser(
            email="delivery-command@example.com", password="Very-secure-pass-123"
        )
        incident = Incident.objects.create(
            category=IncidentCategory.objects.get(slug="crime"),
            description="Native administration workflow test.",
            latitude="-24.628200",
            longitude="25.923100",
        )
        self.client.force_login(admin_user)

        workspace = self.client.get(reverse("admin_delivery_engine"))
        self.assertEqual(workspace.status_code, 200)
        self.assertContains(workspace, "Delivery command")
        self.assertContains(workspace, "overview-subtitle-strip")
        self.assertContains(workspace, "One accountable queue")
        self.assertContains(workspace, "Unified operational queue")
        self.assertContains(workspace, "Users & access")
        self.assertContains(workspace, "admin-platform-nav")
        self.assertContains(workspace, "admin-account-menu")
        self.assertContains(workspace, "css/admin.css")
        self.assertNotContains(workspace, "app-sidebar")
        self.assertRedirects(
            self.client.get(reverse("delivery_command")),
            reverse("admin_delivery_engine"),
        )

        detail = self.client.get(reverse("admin_delivery_case_detail", args=[incident.delivery_case.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, incident.reference)
        self.assertContains(detail, "Service commitments")
        self.assertContains(detail, "Authority handoff")

        native_detail_url = reverse("admin_delivery_case_detail", args=[incident.delivery_case.pk])
        action = self.client.post(
            reverse("delivery_case_action", args=[incident.delivery_case.pk]),
            {"action": "acknowledge", "next": native_detail_url},
        )
        self.assertRedirects(action, native_detail_url)

    def test_non_staff_cannot_open_native_delivery_admin(self):
        resident = User.objects.create_user(
            email="not-staff@example.com", password="Very-secure-pass-123"
        )
        self.client.force_login(resident)
        response = self.client.get(reverse("admin_delivery_engine"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)

    def test_unsafe_eval_is_not_enabled_on_citizen_pages(self):
        response = self.client.get(reverse("home"))
        self.assertNotIn("'unsafe-eval'", response.headers["Content-Security-Policy"])
