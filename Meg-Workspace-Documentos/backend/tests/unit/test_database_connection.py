"""Database DSN/TLS and migration-role contracts for hosted PostgreSQL."""
from __future__ import annotations

from ssl import CERT_REQUIRED, SSLContext

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.config import Settings
from app.db.connection import build_database_connection


def _production_settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "K8pQ4vN7xR2mL9cT5wY3aB6dF1hJ8sZ4qP7nM2vX9cR5",
        "DEBUG": False,
        "DATABASE_URL": "postgresql+asyncpg://runtime:runtime-pass@db.example.supabase.co:5432/postgres",
        "MIGRATION_DATABASE_URL": "postgresql+asyncpg://migrator:migration-pass@db.example.supabase.co:5432/postgres",
        "DATABASE_SSL_MODE": "verify-full",
        "REDIS_URL": "redis://redis.example.net:6379/0",
        "CELERY_BROKER_URL": "redis://redis.example.net:6379/1",
        "CELERY_RESULT_BACKEND": "redis://redis.example.net:6379/2",
        "CORS_ALLOWED_ORIGINS": ["https://app.example.com"],
        "SUPABASE_URL": "https://project-ref.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-role-key-never-used",
        "ENCRYPTION_MASTER_KEY": "encryption-master-test-key-012345678901234567890123",
    }
    values.update(overrides)
    return Settings(**values)


def test_postgres_sslmode_is_translated_to_asyncpg_ssl_context():
    connection = build_database_connection(
        "postgresql://meg:secret@db.example.supabase.co:5432/postgres?sslmode=verify-full"
    )

    assert connection.url.startswith("postgresql+asyncpg://")
    assert "sslmode=" not in connection.url
    context = connection.connect_args["ssl"]
    assert isinstance(context, SSLContext)
    assert context.verify_mode == CERT_REQUIRED
    assert context.check_hostname is True
    assert connection.ssl_mode == "verify-full"


def test_supabase_sslmode_require_is_upgraded_to_verified_tls():
    connection = build_database_connection(
        "postgresql://meg:secret@db.example.supabase.co:5432/postgres?sslmode=require"
    )

    assert connection.ssl_mode == "verify-full"
    assert connection.connect_args["ssl"].verify_mode == CERT_REQUIRED
    assert connection.connect_args["ssl"].check_hostname is True
    assert "sslmode" not in connection.url


def test_explicit_ssl_mode_and_root_ca_are_applied(tmp_path):
    ca_file = tmp_path / "root-ca.pem"
    ca_file.write_text("not-a-real-certificate", encoding="ascii")

    with pytest.raises((OSError, ValueError)):
        build_database_connection(
            "postgresql://meg:secret@db.example.supabase.co:5432/postgres",
            ssl_mode="verify-full",
            ssl_root_cert=str(ca_file),
        )


def test_verify_ca_checks_chain_without_hostname_matching():
    connection = build_database_connection(
        "postgresql://meg:secret@db.example.supabase.co:5432/postgres",
        ssl_mode="verify-ca",
    )

    assert connection.connect_args["ssl"].verify_mode == CERT_REQUIRED
    assert connection.connect_args["ssl"].check_hostname is False


def test_invalid_ssl_mode_is_rejected():
    with pytest.raises(ValueError, match="DATABASE_SSL_MODE"):
        build_database_connection(
            "postgresql://meg:secret@db.example.supabase.co:5432/postgres",
            ssl_mode="prefer",
        )


def test_sqlite_remains_tls_free_for_unit_tests():
    connection = build_database_connection("sqlite+aiosqlite:///./test.db")

    assert connection.url == "sqlite+aiosqlite:///./test.db"
    assert connection.connect_args == {}
    assert connection.ssl_mode is None


def test_migration_connection_uses_separate_ddl_credential():
    settings = _production_settings()

    assert make_url(settings.migration_database_connection.url).username == "migrator"
    assert make_url(settings.database_connection.url).username == "runtime"
    assert make_url(settings.migration_database_connection.url).database == "postgres"
    assert settings.migration_database_connection.ssl_mode == "verify-full"


def test_alembic_rejects_missing_production_migration_connection():
    settings = _production_settings(MIGRATION_DATABASE_URL=None)

    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
        _ = settings.migration_database_connection


def test_migration_connection_must_target_the_same_database():
    settings = _production_settings(
        MIGRATION_DATABASE_URL="postgresql+asyncpg://migrator:migration-pass@db.example.supabase.co:5432/other_database"
    )

    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
        _ = settings.migration_database_connection


def test_alembic_rejects_same_login_for_runtime_and_migrations():
    settings = _production_settings(
        MIGRATION_DATABASE_URL="postgresql+asyncpg://runtime:other-pass@db.example.supabase.co:5432/postgres"
    )

    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
        _ = settings.migration_database_connection


def test_production_rejects_unverified_or_disabled_database_tls():
    with pytest.raises(ValidationError, match="DATABASE_SSL_MODE"):
        _production_settings(DATABASE_SSL_MODE="disable")


def test_tezcatlipoca_uses_the_canonical_megalodon_engine():
    # Import app.main first: that module registers the legacy Tezcatlipoca
    # package path before importing its database module.
    import app.main  # noqa: F401
    from app.models.base import engine as megalodon_engine
    from db.models import engine as tezcatlipoca_engine

    assert tezcatlipoca_engine is megalodon_engine
