import os
import json
import subprocess
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from posts.db_backups import (
    backup_object_key,
    build_manifest,
    encode_manifest,
    gzip_bytes,
    latest_manifest_key,
    normalize_backup_prefix,
    parse_excluded_tables,
    sha256_digest,
)


class Command(BaseCommand):
    # Django exposes this as manage.py backup_postgres_if_changed.
    help = "Create a compressed PostgreSQL backup and upload it to S3 only when the dump changes."

    def add_arguments(self, parser):
        # add_arguments extends Django's command parser with command-specific flags.
        parser.add_argument("--bucket", help="Destination S3 bucket. Defaults to DB_BACKUP_BUCKET or AWS_STORAGE_BUCKET_NAME.")
        parser.add_argument("--prefix", help="Destination key prefix. Defaults to DB_BACKUP_PREFIX.")
        parser.add_argument("--force", action="store_true", help="Upload a backup even when the digest matches the latest manifest.")
        parser.add_argument("--dry-run", action="store_true", help="Compute the dump and digest without uploading anything.")

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        engine = database.get("ENGINE", "")
        if "postgresql" not in engine:
            raise CommandError("backup_postgres_if_changed only supports PostgreSQL databases.")

        bucket = options["bucket"] or os.environ.get("DB_BACKUP_BUCKET") or settings.AWS_STORAGE_BUCKET_NAME
        if not bucket:
            raise CommandError("Set DB_BACKUP_BUCKET or AWS_STORAGE_BUCKET_NAME before running backups.")

        prefix = normalize_backup_prefix(
            options["prefix"]
            or os.environ.get("DB_BACKUP_PREFIX")
            or f"backups/postgres/{database.get('NAME', 'default')}"
        )
        if not prefix:
            raise CommandError("Backup prefix resolved to an empty value.")

        excluded_tables = parse_excluded_tables(os.environ.get("DB_BACKUP_EXCLUDED_TABLES"))
        dump_bytes = self._run_pg_dump(database, excluded_tables)
        digest = sha256_digest(dump_bytes)
        manifest_key = latest_manifest_key(prefix)

        s3 = boto3.client("s3", region_name=os.environ.get("AWS_S3_REGION_NAME") or settings.AWS_S3_REGION_NAME)
        latest_manifest = self._load_latest_manifest(s3, bucket, manifest_key)

        if latest_manifest and latest_manifest.get("sha256") == digest and not options["force"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No PostgreSQL changes detected for {database['NAME']}; latest backup digest is still {digest[:12]}."
                )
            )
            return

        created_at = datetime.now(UTC)
        backup_key = backup_object_key(prefix, database["NAME"], digest, created_at)
        manifest = build_manifest(
            digest=digest,
            backup_key=backup_key,
            database_name=database["NAME"],
            database_host=database.get("HOST") or "localhost",
            dump_size_bytes=len(dump_bytes),
            created_at=created_at,
        )

        if options["dry_run"]:
            self.stdout.write(f"Would upload s3://{bucket}/{backup_key}")
            self.stdout.write(encode_manifest(manifest).decode("utf-8"))
            return

        compressed_dump = gzip_bytes(dump_bytes)
        s3.put_object(
            Bucket=bucket,
            Key=backup_key,
            Body=compressed_dump,
            ContentType="application/gzip",
            Metadata={"sha256": digest},
        )
        s3.put_object(
            Bucket=bucket,
            Key=manifest_key,
            Body=encode_manifest(manifest),
            ContentType="application/json",
        )

        self.stdout.write(self.style.SUCCESS(f"Uploaded PostgreSQL backup to s3://{bucket}/{backup_key}"))

    def _load_latest_manifest(self, s3, bucket, key):
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"NoSuchKey", "404"}:
                return None
            raise CommandError(f"Unable to read s3://{bucket}/{key}: {exc}") from exc
        return json.loads(response["Body"].read().decode("utf-8"))

    def _run_pg_dump(self, database, excluded_tables):
        env = os.environ.copy()
        password = database.get("PASSWORD") or env.get("PGPASSWORD")
        if password:
            env["PGPASSWORD"] = str(password)

        command = [
            "pg_dump",
            "--dbname",
            database["NAME"],
            "--host",
            str(database.get("HOST") or "localhost"),
            "--port",
            str(database.get("PORT") or "5432"),
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--encoding=UTF8",
        ]
        if database.get("USER"):
            command.extend(["--username", str(database["USER"])])
        for table in excluded_tables:
            command.extend(["--exclude-table", table])

        try:
            result = subprocess.run(command, check=True, capture_output=True, env=env)
        except FileNotFoundError as exc:
            raise CommandError("pg_dump is not installed in this image.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            raise CommandError(f"pg_dump failed: {stderr}") from exc

        return result.stdout
