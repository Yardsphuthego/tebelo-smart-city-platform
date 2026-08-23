from django.core.management.base import BaseCommand
from django.db import transaction

from operations.delivery import ensure_command_coverage
from operations.models import (
    IncidentCategory,
    Location,
    Organisation,
    ServiceDeskCase,
    ServiceRoutingPolicy,
)


OFFICIAL_ORGANISATIONS = (
    {
        "short_name": "TEBELO-CMD",
        "name": "TEBELO Gaborone Command Centre",
        "kind": Organisation.Kind.GOVERNMENT,
        "integration_status": Organisation.IntegrationStatus.CONNECTED,
        "source_url": "",
        "emergency_phone": "",
    },
    {
        "short_name": "BPS-GAB",
        "name": "Botswana Police Service — Gaborone",
        "kind": Organisation.Kind.POLICE,
        "emergency_phone": "999",
        "source_url": "https://www.gov.bw/ministries/botswana-police-service",
    },
    {
        "short_name": "BPS-TRAFFIC",
        "name": "Botswana Police Service — Traffic Branch",
        "kind": Organisation.Kind.TRAFFIC,
        "emergency_phone": "999",
        "source_url": "https://www.gov.bw/ministries/botswana-police-service",
    },
    {
        "short_name": "GCC",
        "name": "Gaborone City Council",
        "kind": Organisation.Kind.COUNCIL,
        "emergency_phone": "+2673657400",
        "source_url": "https://www.gov.bw/local-authorities-view",
    },
    {
        "short_name": "GCC-FIRE",
        "name": "Gaborone City Council Fire and Rescue",
        "kind": Organisation.Kind.FIRE,
        "emergency_phone": "998",
        "source_url": "https://www.gov.bw/local-authorities-view",
    },
    {
        "short_name": "MOH-EMS",
        "name": "Ministry of Health — Emergency Medical Services",
        "kind": Organisation.Kind.MEDICAL,
        "emergency_phone": "997",
        "source_url": "https://gov.bw/public-health-services/emergency-medical-services-ambulance-services",
    },
    {
        "short_name": "WUC",
        "name": "Water Utilities Corporation",
        "kind": Organisation.Kind.WATER,
        "emergency_phone": "",
        "source_url": "https://www.gov.bw/ministries/ministry-lands-and-water-affairs",
    },
    {
        "short_name": "BPC",
        "name": "Botswana Power Corporation",
        "kind": Organisation.Kind.ELECTRICITY,
        "emergency_phone": "",
        "source_url": "https://gov.bw/ministries/ministry-minerals-and-energy",
    },
    {
        "short_name": "NDMO",
        "name": "National Disaster Management Office",
        "kind": Organisation.Kind.DISASTER,
        "emergency_phone": "+2673950800",
        "source_url": "https://www.gov.bw/public-safety/assistance-during-national-disasters",
    },
    {
        "short_name": "MCI-DTCO",
        "name": "Ministry of Communications and Innovation — Digital Transformation Coordination Office",
        "kind": Organisation.Kind.GOVERNMENT,
        "emergency_phone": "17779",
        "source_url": "https://gov.bw/ministries/ministry-communications-and-innovation",
    },
)

INCIDENT_ROUTES = {
    "crime": "BPS-GAB",
    "suspicious-activity": "BPS-GAB",
    "dangerous-driving": "BPS-TRAFFIC",
    "road-accident": "BPS-TRAFFIC",
    "fire": "GCC-FIRE",
    "medical-emergency": "MOH-EMS",
    "flooding": "NDMO",
    "water-problem": "WUC",
    "electricity-problem": "BPC",
    "traffic-light": "GCC",
    "pothole": "GCC",
    "blocked-road": "GCC",
    "broken-streetlight": "GCC",
    "damaged-infrastructure": "GCC",
    "illegal-dumping": "GCC",
    "community-concern": "GCC",
}

SERVICE_ROUTES = (
    (ServiceDeskCase.Desk.POLICE, ServiceDeskCase.RequestType.POLICE_ASSISTANCE, "BPS-GAB"),
    (ServiceDeskCase.Desk.POLICE, ServiceDeskCase.RequestType.POLICE_FOLLOW_UP, "BPS-GAB"),
    (ServiceDeskCase.Desk.POLICE, ServiceDeskCase.RequestType.CRIME_PREVENTION, "BPS-GAB"),
    (ServiceDeskCase.Desk.POLICE, ServiceDeskCase.RequestType.OTHER, "BPS-GAB"),
    (ServiceDeskCase.Desk.TRAFFIC, ServiceDeskCase.RequestType.TRAFFIC_ASSISTANCE, "BPS-TRAFFIC"),
    (ServiceDeskCase.Desk.TRAFFIC, ServiceDeskCase.RequestType.OTHER, "BPS-TRAFFIC"),
    (ServiceDeskCase.Desk.FIRE, ServiceDeskCase.RequestType.FIRE_SAFETY, "GCC-FIRE"),
    (ServiceDeskCase.Desk.FIRE, ServiceDeskCase.RequestType.OTHER, "GCC-FIRE"),
    (ServiceDeskCase.Desk.GOVERNMENT, ServiceDeskCase.RequestType.GOVERNMENT_INFORMATION, "MCI-DTCO"),
    (ServiceDeskCase.Desk.GOVERNMENT, ServiceDeskCase.RequestType.APPLICATION_GUIDANCE, "MCI-DTCO"),
    (ServiceDeskCase.Desk.GOVERNMENT, ServiceDeskCase.RequestType.SERVICE_REFERRAL, "MCI-DTCO"),
    (ServiceDeskCase.Desk.GOVERNMENT, ServiceDeskCase.RequestType.OTHER, "MCI-DTCO"),
)

INCIDENT_SLA = {
    "critical": (3, 8, 240),
    "high": (5, 16, 480),
    "medium": (15, 30, 1440),
    "low": (30, 120, 4320),
}


class Command(BaseCommand):
    help = "Idempotently configure verified Gaborone authority desks and baseline routing policies."

    @transaction.atomic
    def handle(self, *args, **options):
        city = Location.objects.get(code="gab", kind=Location.Kind.CITY)
        organisations = {}
        for specification in OFFICIAL_ORGANISATIONS:
            values = {
                **specification,
                "location": city,
                "is_active": True,
            }
            short_name = values.pop("short_name")
            values.setdefault("integration_status", Organisation.IntegrationStatus.ONBOARDING)
            organisation, _ = Organisation.objects.update_or_create(
                short_name=short_name,
                defaults=values,
            )
            organisations[short_name] = organisation

        command_centre = organisations["TEBELO-CMD"]
        for slug, destination in INCIDENT_ROUTES.items():
            category = IncidentCategory.objects.get(slug=slug)
            acknowledgement, assignment, resolution = INCIDENT_SLA[category.default_priority]
            ServiceRoutingPolicy.objects.update_or_create(
                name=f"Gaborone · {category.name}",
                defaults={
                    "case_type": ServiceRoutingPolicy.CaseType.INCIDENT,
                    "incident_category": category,
                    "incident_priority": "",
                    "service_desk": "",
                    "service_request_type": "",
                    "destination_organisation": organisations[destination],
                    "escalation_organisation": command_centre,
                    "acknowledgement_minutes": acknowledgement,
                    "assignment_minutes": assignment,
                    "resolution_minutes": resolution,
                    "repeat_escalation_minutes": 30,
                    "precedence": 10,
                    "is_active": True,
                },
            )

        for desk, request_type, destination in SERVICE_ROUTES:
            label = ServiceDeskCase.RequestType(request_type).label
            ServiceRoutingPolicy.objects.update_or_create(
                name=f"Gaborone virtual service · {desk} · {label}",
                defaults={
                    "case_type": ServiceRoutingPolicy.CaseType.VIRTUAL_SERVICE,
                    "incident_category": None,
                    "incident_priority": "",
                    "service_desk": desk,
                    "service_request_type": request_type,
                    "destination_organisation": organisations[destination],
                    "escalation_organisation": command_centre,
                    "acknowledgement_minutes": 30,
                    "assignment_minutes": 120,
                    "resolution_minutes": 2880,
                    "repeat_escalation_minutes": 120,
                    "precedence": 10,
                    "is_active": True,
                },
            )

        ensure_command_coverage()
        self.stdout.write(self.style.SUCCESS(
            f"Configured {len(organisations)} organisations, "
            f"{len(INCIDENT_ROUTES)} incident routes and {len(SERVICE_ROUTES)} virtual-service routes."
        ))
