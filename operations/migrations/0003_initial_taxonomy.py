from django.db import migrations

CATEGORIES = [
    ("Crime", "crime", "safety", "police", "high"),
    ("Suspicious activity", "suspicious-activity", "safety", "police", "medium"),
    ("Road accident", "road-accident", "traffic", "traffic", "high"),
    ("Dangerous driving", "dangerous-driving", "traffic", "traffic", "high"),
    ("Blocked road", "blocked-road", "traffic", "roads", "medium"),
    ("Damaged traffic light", "traffic-light", "infrastructure", "traffic", "medium"),
    ("Fire", "fire", "fire", "fire", "critical"),
    ("Medical emergency", "medical-emergency", "medical", "medical", "critical"),
    ("Flooding", "flooding", "environment", "disaster", "high"),
    ("Broken streetlight", "broken-streetlight", "infrastructure", "council", "low"),
    ("Pothole", "pothole", "infrastructure", "roads", "medium"),
    ("Illegal dumping", "illegal-dumping", "environment", "council", "low"),
    ("Damaged public infrastructure", "damaged-infrastructure", "infrastructure", "council", "medium"),
    ("Electricity problem", "electricity-problem", "utilities", "electricity", "medium"),
    ("Water problem", "water-problem", "utilities", "water", "medium"),
    ("Other community concern", "community-concern", "community", "council", "medium"),
]


def seed(apps, schema_editor):
    Location = apps.get_model("operations", "Location")
    Category = apps.get_model("operations", "IncidentCategory")
    botswana, _ = Location.objects.get_or_create(name="Botswana", code="bw", kind="country", parent=None)
    south_east, _ = Location.objects.get_or_create(name="South-East District", code="se", kind="district", parent=botswana)
    Location.objects.get_or_create(name="Gaborone", code="gab", kind="city", parent=south_east, defaults={"centre_latitude": -24.628208, "centre_longitude": 25.923147})
    for name, slug, domain, route, priority in CATEGORIES:
        Category.objects.get_or_create(slug=slug, defaults={"name": name, "domain": domain, "routes_to": route, "default_priority": priority})


def unseed(apps, schema_editor):
    Category = apps.get_model("operations", "IncidentCategory")
    Category.objects.filter(slug__in=[row[1] for row in CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_postgis_incident_point")]
    operations = [migrations.RunPython(seed, unseed)]

