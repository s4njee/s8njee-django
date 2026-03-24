import gzip
import hashlib
import json
import re
from datetime import datetime, UTC


DEFAULT_EXCLUDED_TABLES = ["django_session"]


def normalize_backup_prefix(prefix):
    return (prefix or "").strip().strip("/")


def parse_excluded_tables(value):
    if not value:
        return list(DEFAULT_EXCLUDED_TABLES)
    return [table.strip() for table in value.split(",") if table.strip()]


def latest_manifest_key(prefix):
    return f"{normalize_backup_prefix(prefix)}/latest.json"


def backup_object_key(prefix, database_name, digest, created_at=None):
    created_at = created_at or datetime.now(UTC)
    safe_database_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", database_name).strip("-") or "database"
    timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{normalize_backup_prefix(prefix)}/{timestamp}-{safe_database_name}-{digest[:12]}.sql.gz"


def gzip_bytes(payload):
    return gzip.compress(payload, mtime=0)


def sha256_digest(payload):
    return hashlib.sha256(payload).hexdigest()


def build_manifest(*, digest, backup_key, database_name, database_host, dump_size_bytes, created_at=None):
    created_at = created_at or datetime.now(UTC)
    return {
        "sha256": digest,
        "backup_key": backup_key,
        "database_name": database_name,
        "database_host": database_host,
        "dump_size_bytes": dump_size_bytes,
        "created_at": created_at.isoformat(),
    }


def encode_manifest(manifest):
    return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
