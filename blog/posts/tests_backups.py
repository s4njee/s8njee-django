from datetime import UTC, datetime

from django.test import TestCase

from .db_backups import backup_object_key, gzip_bytes, normalize_backup_prefix, sha256_digest


class PostgresBackupHelperTests(TestCase):
    def test_backup_object_key_is_stable_and_namespaced(self):
        created_at = datetime(2026, 3, 24, 7, 15, tzinfo=UTC)

        key = backup_object_key("backups/postgres/netcup/s8njee", "s8njee", "abc123def4567890", created_at)

        self.assertEqual(
            key,
            "backups/postgres/netcup/s8njee/20260324T071500Z-s8njee-abc123def456.sql.gz",
        )

    def test_gzip_bytes_and_digest_are_deterministic(self):
        payload = b"select 1;\n"

        self.assertEqual(normalize_backup_prefix("/backups/postgres/mars/"), "backups/postgres/mars")
        self.assertEqual(sha256_digest(payload), sha256_digest(payload))
        self.assertEqual(gzip_bytes(payload), gzip_bytes(payload))
