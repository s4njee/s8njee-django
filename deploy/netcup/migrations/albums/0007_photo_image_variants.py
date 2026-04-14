from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("albums", "0006_album_cover_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="photo",
            name="image_medium",
            field=models.ImageField(blank=True, upload_to="photos/%Y/%m/%d/"),
        ),
        migrations.AddField(
            model_name="photo",
            name="image_small",
            field=models.ImageField(blank=True, upload_to="photos/%Y/%m/%d/"),
        ),
    ]
