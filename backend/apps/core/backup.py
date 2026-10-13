"""Backup & restore helpers (pg_dump custom format + media archive + manifest with row counts)."""
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

KEY_TABLES = ["accounts_user", "reports_report", "reports_reportevent", "finance_ledgerentry", "finance_payment",
              "inventory_resource", "inventory_reservation", "community_initiative", "core_auditlog", "geo_area",
              "core_mediaasset", "roadnow_roadalert"]


def _env(db):
    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = db["PASSWORD"]
    return env


def _conn_args(db, name=None):
    args = ["-h", db.get("HOST") or "localhost", "-p", str(db.get("PORT") or 5432), "-U", db["USER"]]
    return args + (["-d", name] if name else [])


def row_counts(using_cursor=None):
    out = {}
    cur = using_cursor or connection.cursor()
    for t in KEY_TABLES:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        out[t] = cur.fetchone()[0]
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup(out_dir=None, include_media=True):
    db = settings.DATABASES["default"]
    out = Path(out_dir or settings.BACKUP_DIR)
    out.mkdir(parents=True, exist_ok=True)
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    dump = out / f"aawen-{stamp}.dump"
    subprocess.run(["pg_dump", "-Fc", "--no-owner", "-f", str(dump)] + _conn_args(db, db["NAME"]), check=True,
                   env=_env(db))
    manifest = {"created_at": timezone.now().isoformat(), "database": db["NAME"], "dump": dump.name,
                "dump_sha256": sha256(dump), "row_counts": row_counts()}
    if include_media and not settings.USE_S3 and Path(settings.MEDIA_ROOT).exists():
        media = out / f"aawen-{stamp}-media.tar.gz"
        with tarfile.open(media, "w:gz") as tar:
            tar.add(settings.MEDIA_ROOT, arcname="media")
        manifest["media"] = media.name
        manifest["media_sha256"] = sha256(media)
    elif settings.USE_S3:
        manifest["media"] = "S3 bucket — use bucket versioning/replication (see docs/OPERATIONS.md)"
    mpath = out / f"aawen-{stamp}.manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return mpath


def restore_backup(manifest_path, target_db, drop_existing=False):
    """Restores into `target_db` (never silently over the live DB) and verifies row counts."""
    db = settings.DATABASES["default"]
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    dump = manifest_path.parent / manifest["dump"]
    if sha256(dump) != manifest["dump_sha256"]:
        raise RuntimeError("checksum mismatch: backup file is corrupted")
    if target_db == db["NAME"] and not drop_existing:
        raise RuntimeError("refusing to restore over the live database without --drop-existing")
    env = _env(db)
    if drop_existing:
        subprocess.run(["dropdb", "--if-exists"] + _conn_args(db) + [target_db], check=True, env=env)
    subprocess.run(["createdb"] + _conn_args(db) + [target_db], check=True, env=env)
    subprocess.run(["psql", "-q", "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"] + _conn_args(db, target_db),
                   check=True, env=env, capture_output=True)
    res = subprocess.run(["pg_restore", "--no-owner", "--exit-on-error", "-d", target_db] + _conn_args(db) + [str(dump)],
                         env=env, capture_output=True, text=True)
    if res.returncode != 0 and "already exists" not in res.stderr:
        raise RuntimeError(res.stderr[-2000:])
    import psycopg
    with psycopg.connect(host=db.get("HOST") or "localhost", port=db.get("PORT") or 5432, user=db["USER"],
                         password=db.get("PASSWORD") or None, dbname=target_db) as conn:
        with conn.cursor() as cur:
            counts = row_counts(cur)
    mismatches = {t: (manifest["row_counts"][t], counts.get(t)) for t in manifest["row_counts"]
                  if manifest["row_counts"][t] != counts.get(t)}
    return {"target": target_db, "counts": counts, "mismatches": mismatches, "ok": not mismatches}
