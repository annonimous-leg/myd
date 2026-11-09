"""Shared, explicit SQLAlchemy connection policy for hosted PostgreSQL.

The helper keeps asyncpg-specific TLS options out of the SQLAlchemy URL.
Never log DatabaseConnection.url: it contains the database credential.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ssl
from typing import Any

from sqlalchemy.engine import make_url


@dataclass(frozen=True, repr=False)
class DatabaseConnection:
    url: str = field(repr=False)
    connect_args: dict[str, Any] = field(repr=False)
    ssl_mode: str | None


def _canonical_ssl_mode(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    mode = value.strip().lower()
    # PostgreSQL/Supabase commonly supplies sslmode=require. For an
    # application connection, prefer full certificate and hostname checks.
    if mode == "require":
        return "verify-full"
    if mode not in {"disable", "verify-ca", "verify-full"}:
        raise ValueError(
            "DATABASE_SSL_MODE must be one of disable, require, verify-ca or verify-full"
        )
    return mode


def build_database_connection(
    raw_url: str,
    *,
    ssl_mode: str | None = None,
    ssl_root_cert: str | None = None,
) -> DatabaseConnection:
    """Normalize a DB URL and build driver arguments without leaking secrets.

    PostgreSQL URLs are normalized to asyncpg. PostgreSQL's libpq
    `sslmode` and `sslrootcert` query parameters are removed and translated
    into asyncpg's `ssl` connect argument. SQLite remains TLS-free.
    """
    try:
        parsed = make_url(str(raw_url).strip())
    except Exception as exc:
        raise ValueError("DATABASE_URL has an invalid SQLAlchemy URL") from exc

    driver = parsed.drivername
    if driver in {"sqlite", "sqlite+aiosqlite"}:
        if ssl_mode or parsed.query.get("sslmode") or ssl_root_cert or parsed.query.get("sslrootcert"):
            raise ValueError("TLS options are not valid for SQLite")
        return DatabaseConnection(
            url=parsed.set(drivername="sqlite+aiosqlite").render_as_string(hide_password=False),
            connect_args={},
            ssl_mode=None,
        )

    if driver in {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg2"}:
        parsed = parsed.set(drivername="postgresql+asyncpg")
    else:
        raise ValueError("DATABASE_URL must use PostgreSQL or SQLite")

    query = dict(parsed.query)
    url_mode = query.pop("sslmode", None)
    url_ca = query.pop("sslrootcert", None)
    if isinstance(url_mode, tuple):
        raise ValueError("DATABASE_URL sslmode must be a single value")
    if isinstance(url_ca, tuple):
        raise ValueError("DATABASE_URL sslrootcert must be a single value")

    configured_mode = _canonical_ssl_mode(ssl_mode)
    embedded_mode = _canonical_ssl_mode(url_mode)
    if configured_mode and embedded_mode and configured_mode != embedded_mode:
        raise ValueError("DATABASE_SSL_MODE conflicts with DATABASE_URL sslmode")
    effective_mode = configured_mode or embedded_mode

    if ssl_root_cert and url_ca and ssl_root_cert != url_ca:
        raise ValueError("DATABASE_SSL_ROOT_CERT conflicts with DATABASE_URL sslrootcert")
    ca_file = ssl_root_cert or url_ca

    connect_args: dict[str, Any] = {}
    if effective_mode == "disable":
        connect_args["ssl"] = False
    elif effective_mode in {"verify-ca", "verify-full"}:
        try:
            context = ssl.create_default_context(cafile=ca_file or None)
        except (OSError, ssl.SSLError) as exc:
            raise ValueError("DATABASE_SSL_ROOT_CERT could not be loaded") from exc
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = effective_mode == "verify-full"
        context.verify_mode = ssl.CERT_REQUIRED
        connect_args["ssl"] = context
    elif ca_file:
        raise ValueError("DATABASE_SSL_ROOT_CERT requires DATABASE_SSL_MODE=verify-ca or verify-full")

    normalized = parsed.set(query=query)
    return DatabaseConnection(
        url=normalized.render_as_string(hide_password=False),
        connect_args=connect_args,
        ssl_mode=effective_mode,
    )
