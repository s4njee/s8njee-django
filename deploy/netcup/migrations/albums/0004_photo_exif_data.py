from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("albums", "0003_photo_async_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="photo",
            name="exif_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
