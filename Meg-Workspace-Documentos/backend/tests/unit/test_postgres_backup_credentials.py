"""Credential handling at the SQLAlchemy URL / libpq process boundary."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy.engine import URL

from scripts.postgres_backup import connection


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+asyncpg", "postgresql+psycopg2"])
def test_libpq_connection_keeps_special_password_out_of_argv_and_environment(monkeypatch, driver):
    secret = "ci@credential:with\\escapes/and%characters"
    url = URL.create(driver, username="backup", password=secret, host="localhost",
                     port=5432, database="recovery", query={"sslmode": "require"})
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    monkeypatch.setenv("PGPASSWORD", "obsolete-ci-password")
    with connection() as (uri, env):
        assert uri == "postgresql://backup@localhost:5432/recovery?sslmode=require"
        assert "DATABASE_URL" not in env and "PGPASSWORD" not in env
        passfile = Path(env["PGPASSFILE"])
        assert passfile.stat().st_mode & 0o077 == 0
        assert passfile.read_text() == "*:*:*:*:ci@credential\\:with\\\\escapes/and%characters\n"
    assert not passfile.exists()


def test_malformed_connection_error_does_not_print_credentials():
    secret = "ci-secret-that-must-not-appear"
    command = Path(__file__).resolve().parents[2] / "scripts" / "postgres_backup.py"
    env = dict(os.environ, DATABASE_URL=f"malformed credential {secret}")
    result = subprocess.run([sys.executable, str(command), "backup"], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert secret not in result.stdout + result.stderr
    assert "input validation failed" in result.stderr
