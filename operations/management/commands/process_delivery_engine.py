from django.core.management.base import BaseCommand

from operations.delivery import (
    ensure_command_coverage,
    process_due_delivery_cases,
    refresh_operational_recommendations,
)


class Command(BaseCommand):
    help = "Process due service-delivery cases, escalations and operational recommendations."

    def handle(self, *args, **options):
        ensure_command_coverage()
        escalated = process_due_delivery_cases()
        recommendations = refresh_operational_recommendations().count()
        self.stdout.write(self.style.SUCCESS(
            f"Delivery engine processed: {escalated} escalation(s), {recommendations} active recommendation(s)."
        ))
