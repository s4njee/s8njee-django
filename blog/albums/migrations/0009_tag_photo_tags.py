from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("albums", "0008_album_slug_photo_alt_text"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("slug", models.SlugField(max_length=100, unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="photo",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="photos", to="albums.tag"),
        ),
    ]
