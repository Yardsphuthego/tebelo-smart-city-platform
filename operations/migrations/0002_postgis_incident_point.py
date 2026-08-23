from django.db import migrations


def add_postgis_point(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("""
            ALTER TABLE operations_incident
            ADD COLUMN IF NOT EXISTS geo_point geography(Point, 4326)
            GENERATED ALWAYS AS (
                ST_SetSRID(ST_MakePoint(longitude::double precision, latitude::double precision), 4326)::geography
            ) STORED
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS operations_incident_geo_gist ON operations_incident USING GIST (geo_point)")


def remove_postgis_point(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS operations_incident_geo_gist")
        cursor.execute("ALTER TABLE operations_incident DROP COLUMN IF EXISTS geo_point")


class Migration(migrations.Migration):
    dependencies = [("operations", "0001_initial")]
    operations = [migrations.RunPython(add_postgis_point, remove_postgis_point)]

