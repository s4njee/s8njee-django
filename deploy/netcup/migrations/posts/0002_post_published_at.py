from django.db import migrations, models


def backfill_published_at(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    Post.objects.filter(published=True, published_at__isnull=True).update(published_at=models.F("created_at"))


def clear_published_at(apps, schema_editor):
    Post = apps.get_model("posts", "Post")
    Post.objects.update(published_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("posts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="published_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_published_at, clear_published_at),
        migrations.AlterModelOptions(
            name="post",
            options={"ordering": ["-published_at", "-created_at"]},
        ),
    ]
