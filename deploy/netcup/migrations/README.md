Netcup migration queue

Use this folder to stage Django migration files that need to be applied the next time we deploy to Netcup.

Workflow:

1. When a new migration is created under `blog/albums/migrations/` or another app, copy the exact migration file into the matching subdirectory here.
2. Keep the staged copy in git until the Netcup rollout has applied it.
3. During the deploy, verify the live pod logs show the migration being applied.
4. Once Netcup has the migration, clear the staged copy or replace it with the next pending migration set.

Current staged migrations:

- `albums/0005_alter_photo_options_photo_sort_order.py`
- `albums/0006_album_cover_photo.py`
