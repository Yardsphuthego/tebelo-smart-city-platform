import django.db.models.deletion
from django.db import migrations, models


def populate_case_references(apps, schema_editor):
    service_case = apps.get_model("operations", "ServiceDeskCase")
    prefixes = {"police": "VP", "government": "GV", "traffic": "TP", "fire": "FE"}
    for case in service_case.objects.filter(reference__isnull=True).iterator():
        prefix = prefixes.get(case.desk, "VS")
        year = case.created_at.year
        case.reference = f"{prefix}-{year}-{case.id.hex[:8].upper()}"
        case.save(update_fields=["reference"])


class Migration(migrations.Migration):
    dependencies = [("operations", "0003_initial_taxonomy")]

    operations = [
        migrations.AlterModelOptions(
            name="servicedeskcase", options={"ordering": ("-updated_at",)}
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="access_context",
            field=models.CharField(
                choices=[
                    ("remote", "No nearby office or police station"),
                    ("mobility", "Mobility or accessibility barrier"),
                    ("digital", "Prefer digital access"),
                    ("other", "Other"),
                ],
                default="digital",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="assigned_organisation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="service_cases",
                to="operations.organisation",
            ),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="location_description",
            field=models.CharField(blank=True, max_length=240),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="preferred_contact",
            field=models.CharField(
                choices=[
                    ("message", "Secure TEBELO message"),
                    ("phone", "Phone callback"),
                    ("sms", "SMS update"),
                ],
                default="message",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="preferred_language",
            field=models.CharField(
                choices=[("en", "English"), ("tn", "Setswana")],
                default="en",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="reference",
            field=models.CharField(
                editable=False, max_length=32, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="request_type",
            field=models.CharField(
                choices=[
                    ("police_assistance", "Police: non-emergency assistance"),
                    ("police_follow_up", "Police: case or report follow-up"),
                    ("crime_prevention", "Police: crime-prevention guidance"),
                    ("government_information", "Government: service information"),
                    ("application_guidance", "Government: application guidance"),
                    ("service_referral", "Government: service referral"),
                    ("traffic_assistance", "Traffic: non-emergency assistance"),
                    ("fire_safety", "Fire: safety guidance"),
                    ("other", "Other assistance"),
                ],
                default="other",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="servicedeskcase",
            name="status",
            field=models.CharField(
                choices=[
                    ("submitted", "Submitted"),
                    ("routed", "Routed"),
                    ("in_progress", "In progress"),
                    ("waiting_resident", "Waiting for resident"),
                    ("resolved", "Resolved"),
                    ("closed", "Closed"),
                ],
                db_index=True,
                default="submitted",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="servicedeskcase",
            name="desk",
            field=models.CharField(
                choices=[
                    ("police", "Virtual Police Station"),
                    ("government", "Government Virtual Assistance"),
                    ("traffic", "Traffic Police"),
                    ("fire", "Fire and emergency"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(
            populate_case_references, reverse_code=migrations.RunPython.noop
        ),
        migrations.AlterField(
            model_name="servicedeskcase",
            name="reference",
            field=models.CharField(editable=False, max_length=32, unique=True),
        ),
        migrations.AddIndex(
            model_name="servicedeskcase",
            index=models.Index(
                fields=["desk", "status", "-created_at"],
                name="operations__desk_4973c9_idx",
            ),
        ),
    ]
