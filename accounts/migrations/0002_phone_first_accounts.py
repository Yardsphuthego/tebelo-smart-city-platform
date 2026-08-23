from django.db import migrations, models

import accounts.phone


def empty_phone_numbers_to_null(apps, schema_editor):
    user = apps.get_model("accounts", "User")
    user.objects.filter(phone_number="").update(phone_number=None)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.RunPython(
            empty_phone_numbers_to_null,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="user",
            name="email",
            field=models.EmailField(
                blank=True, max_length=254, null=True, unique=True
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="phone_number",
            field=models.CharField(
                blank=True,
                max_length=16,
                null=True,
                unique=True,
                validators=[accounts.phone.validate_phone_number],
            ),
        ),
    ]
