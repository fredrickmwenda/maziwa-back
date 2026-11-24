"""Nightly backup:  python manage.py backup_db   (cron, or the `backup` service in docker-compose)."""
import gzip
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Dump the database to BACKUP_DIR (gzip), delete old backups, optionally copy to S3."

    def handle(self, *args, **opts):
        dest = Path(settings.BACKUP_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        db = settings.DATABASES["default"]
        if "sqlite" in db["ENGINE"]:
            out, raw = dest / f"maziwa-{stamp}.sqlite3.gz", dest / f"_tmp-{stamp}.sqlite3"
            src, dst = sqlite3.connect(db["NAME"]), sqlite3.connect(raw)
            with dst:
                src.backup(dst)
            src.close(); dst.close()
            with open(raw, "rb") as fi, gzip.open(out, "wb") as fo:
                shutil.copyfileobj(fi, fo)
            raw.unlink()
        else:
            out = dest / f"maziwa-{stamp}.sql.gz"
            env = dict(os.environ, PGPASSWORD=str(db.get("PASSWORD", "")))
            cmd = ["pg_dump", "-h", str(db["HOST"]), "-p", str(db["PORT"]), "-U", db["USER"], "-d", db["NAME"], "--no-owner"]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env)
            except FileNotFoundError:
                raise CommandError("pg_dump is not installed (apt install postgresql-client).")
            with gzip.open(out, "wb") as fo:
                shutil.copyfileobj(proc.stdout, fo)
            if proc.wait() != 0:
                out.unlink(missing_ok=True)
                raise CommandError("pg_dump failed")
        self.stdout.write(f"Backup written: {out} ({out.stat().st_size // 1024} KB)")

        cutoff = time.time() - settings.BACKUP_KEEP_DAYS * 86400
        for f in dest.glob("maziwa-*"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                self.stdout.write(f"Deleted old backup {f.name}")

        if settings.BACKUP_S3_BUCKET:
            try:
                import boto3
                boto3.client("s3").upload_file(str(out), settings.BACKUP_S3_BUCKET, f"maziwa-backups/{out.name}")
                self.stdout.write(f"Copied to s3://{settings.BACKUP_S3_BUCKET}")
            except Exception as e:
                raise CommandError(f"S3 upload failed: {e}")
