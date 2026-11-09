"""Logical PostgreSQL backup and recovery into an empty, isolated database."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

from sqlalchemy.engine import make_url, URL
from sqlalchemy.exc import ArgumentError


class BackupInputError(ValueError):
    """A deliberately sanitized, actionable input error."""


# template0 has public plus system namespaces and the built-in plpgsql extension.
# Relations alone do not identify an empty database: routines, standalone types,
# extensions and schemas could otherwise survive an apparently clean restore.
EMPTY_DATABASE_SQL = """
WITH user_namespaces AS (
    SELECT oid, nspname FROM pg_namespace
    WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
)
SELECT
    (SELECT count(*) FROM pg_class WHERE relnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_proc WHERE pronamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_type WHERE typnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_namespace WHERE nspname !~ '^pg_'
       AND nspname NOT IN ('public', 'information_schema'))
  + (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql')
  + (SELECT count(*) FROM pg_collation WHERE collnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_conversion WHERE connamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_operator WHERE oprnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_opclass WHERE opcnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_opfamily WHERE opfnamespace IN (SELECT oid FROM user_namespaces))
  + (SELECT count(*) FROM pg_event_trigger)
  + (SELECT count(*) FROM pg_foreign_server)
  + (SELECT count(*) FROM pg_foreign_data_wrapper)
  + (SELECT count(*) FROM pg_publication)
  + (SELECT count(*) FROM pg_largeobject_metadata)
"""


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@contextmanager
def connection():
    url = make_url(os.environ["DATABASE_URL"])
    if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2", "postgresql+psycopg"}:
        raise BackupInputError("PostgreSQL DATABASE_URL required")
    if not url.database or any(k.lower() in {"password", "passfile", "sslpassword"} for k in url.query):
        raise BackupInputError("Explicit database required; credentials belong in URI userinfo or PGPASSFILE")
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.pop("PGPASSWORD", None)
    # Translate the application's SQLAlchemy dialect to the libpq URI contract.
    # Never expose a password through process arguments or exception messages.
    uri = URL.create("postgresql", username=url.username, host=url.host, port=url.port,
                     database=url.database, query=url.query).render_as_string(hide_password=False)
    with tempfile.TemporaryDirectory(prefix="meg-pgpass-") as directory:
        if url.password is not None:
            if any(c in url.password for c in "\r\n\0"):
                raise BackupInputError("Password contains characters unsupported by PostgreSQL password files")
            passfile = Path(directory) / "passfile"
            escaped = url.password.replace("\\", "\\\\").replace(":", "\\:")
            passfile.touch(mode=0o600)
            passfile.write_text(f"*:*:*:*:{escaped}\n")
            env["PGPASSFILE"] = str(passfile)
        yield uri, env


def run(args, env, capture=False):
    # No interactive password prompt; libpq takes credentials from the passfile.
    return subprocess.run(args, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None)


def backup(uri, env):
    directory = Path(os.getenv("BACKUP_DIR", "/var/backups/megalodon"))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = directory / f"megalodon_{stamp}_{uuid4().hex}.dump"
    # Publish only a complete dump and checksum. mkstemp provides private modes.
    fd, temporary = tempfile.mkstemp(prefix=".incomplete-", dir=directory)
    os.close(fd)
    temporary = Path(temporary)
    checksum = Path(str(destination) + ".sha256")
    try:
        run(["pg_dump", "--no-password", "--dbname", uri, "--format=custom",
             "--no-owner", "--no-privileges", "--file", str(temporary)], env)
        with temporary.open("rb") as source:
            os.fsync(source.fileno())
        value = digest(temporary)
        temporary.replace(destination)
        with checksum.open("x", encoding="utf-8") as output:
            os.chmod(checksum, 0o600)
            output.write(f"{value}  {destination.name}\n")
            output.flush()
            os.fsync(output.fileno())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        checksum.unlink(missing_ok=True)
        raise
    print(destination.resolve())


def restore(uri, env, source=None):
    source = Path(source if source is not None else os.environ["BACKUP_FILE"])
    if not source.is_file():
        raise BackupInputError("Backup file missing")
    checksum = Path(str(source) + ".sha256")
    if not checksum.is_file():
        raise BackupInputError("Backup checksum file required")
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)\n?", checksum.read_text())
    if not match or match[2] != source.name or not hmac.compare_digest(match[1], digest(source)):
        raise BackupInputError("Backup checksum mismatch")
    # Never clean a live installation. Recovery is a separate deployment step.
    objects = run(["psql", "--no-password", "--dbname", uri, "-X", "-qAt",
                   "-v", "ON_ERROR_STOP=1", "-c",
                   EMPTY_DATABASE_SQL], env, capture=True).stdout.strip()
    if objects != "0":
        raise BackupInputError("Restore requires an empty isolated database; existing objects must not be overwritten")
    run(["pg_restore", "--no-password", "--dbname", uri, "--single-transaction",
         "--exit-on-error", "--no-owner", "--no-privileges", str(source)], env)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"backup", "restore"}:
        raise SystemExit("Usage: postgres_backup.py backup|restore")
    os.umask(0o077)
    try:
        with connection() as (uri, env):
            (backup if sys.argv[1] == "backup" else restore)(uri, env)
    except BackupInputError as exc:
        raise SystemExit(str(exc)) from None
    except (ValueError, KeyError, ArgumentError):
        # Avoid parser errors that may embed credentials in the original URL.
        raise SystemExit("Backup/recovery input validation failed") from None


if __name__ == "__main__":
    main()
