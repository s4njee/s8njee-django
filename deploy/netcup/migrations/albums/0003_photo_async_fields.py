from django.db import migrations, models


def backfill_status(apps, schema_editor):
    Photo = apps.get_model("albums", "Photo")
    Photo.objects.all().update(status="ready")


class Migration(migrations.Migration):
    dependencies = [
        ("albums", "0002_photo_thumbnail"),
    ]

    operations = [
        migrations.AddField(
            model_name="photo",
            name="original",
            field=models.FileField(blank=True, upload_to="photos/originals/%Y/%m/%d/"),
        ),
        migrations.AddField(
            model_name="photo",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("processing", "Processing"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="photo",
            name="error",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="photo",
            name="image",
            field=models.ImageField(blank=True, upload_to="photos/%Y/%m/%d/"),
        ),
        migrations.AlterField(
            model_name="photo",
            name="thumbnail",
            field=models.ImageField(blank=True, upload_to="photos/%Y/%m/%d/thumbs/"),
        ),
        migrations.RunPython(backfill_status, migrations.RunPython.noop),
    ]
