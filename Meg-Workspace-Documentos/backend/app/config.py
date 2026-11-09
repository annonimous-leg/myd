# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Configuración centralizada de Megalodon v4.
Todas las variables de entorno se validan con Pydantic v2.
"""
from enum import Enum
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class FailurePolicy(str, Enum):
    """Política de falla para controles de seguridad dependientes de Redis."""
    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class Settings(BaseSettings):
    """Configuración del sistema Megalodon."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── App ───────────────────────────────────────────────
    APP_NAME: str = "Megalodon CostOS v4"
    APP_VERSION: str = "4.0.0"
    ENVIRONMENT: str = Field(default="development", pattern=r"^(development|staging|production)$")
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # ─── Database ────────────────────────────────────────────
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./megalodon_dev.db")
    # DDL-only principal connection for Alembic. Runtime never receives it.
    MIGRATION_DATABASE_URL: Optional[str] = None
    DATABASE_SSL_MODE: Optional[str] = Field(
        default=None, pattern=r"^(disable|require|verify-ca|verify-full)$"
    )
    DATABASE_SSL_ROOT_CERT: Optional[str] = None
    DATABASE_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)

    @field_validator("DATABASE_URL")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        value = v.strip()
        if value.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://", "sqlite://", "sqlite+aiosqlite://")):
            return value
        raise ValueError("DATABASE_URL debe ser postgres/postgresql o sqlite+aiosqlite")

    @field_validator("MIGRATION_DATABASE_URL")
    @classmethod
    def _validate_migration_database_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        value = v.strip()
        if not value.startswith(("postgres://", "postgresql://", "postgresql+asyncpg://")):
            raise ValueError("MIGRATION_DATABASE_URL debe ser una URL PostgreSQL")
        return value

    # ─── Redis ───────────────────────────────────────────────
    REDIS_URL: RedisDsn = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: RedisDsn = Field(default="redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: RedisDsn = Field(default="redis://localhost:6379/2")

    # ─── Security ────────────────────────────────────────────
    SECRET_KEY: str = Field(default="dev-secret-key-32-chars-long-1234567890ab", min_length=32)
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, ge=1)
    # Master key para envelope encryption de documentos. En producción debe
    # ser diferente a SECRET_KEY y rotarse mediante re-wrap de las DEKs.
    # En dev/staging puede quedar vacía y se usa SECRET_KEY como fallback
    # (no recomendado para producción -- ver crypto.py).
    ENCRYPTION_MASTER_KEY: Optional[str] = Field(default=None, min_length=32)

    # ─── Seguridad operativa / degradación controlada ─────────
    # Se usa por token_revocation.py y rate_limit.py. En desarrollo
    # puede ir en fail_open para no bloquear flujo local si Redis no
    # está arriba; en producción lo normal es fail_closed.
    SECURITY_PROTECTION_FAILURE_POLICY: Optional[FailurePolicy] = None

    # ─── S3 / MinIO (legado / opcional) ───────────────────────
    # La especificación final del sistema usa Supabase (Postgres + Storage)
    # como proveedor único -- ver sección "Supabase" abajo. Estas variables
    # se dejan por si algún día se vuelve a un storage self-hosted, pero
    # SupabaseStorage (app/integrations/supabase_storage.py) es la ruta
    # activa hoy.
    S3_ENDPOINT: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    S3_BUCKET: str = "megalodon-uploads"
    S3_REGION: str = "us-east-1"

    # ─── Supabase (Storage; Postgres se configura vía DATABASE_URL) ──
    SUPABASE_URL: Optional[str] = None
    # Service role key: el backend actúa como identidad de servicio de
    # confianza, no como un usuario final autenticado en Supabase. La
    # fuente de verdad de auth sigue siendo este backend (JWT propio),
    # Supabase aquí es solo infraestructura de storage.
    SUPABASE_SERVICE_KEY: Optional[str] = None
    SUPABASE_BUCKET_BIM: str = "bim-modelos"
    SUPABASE_BUCKET_DOCUMENTOS: str = "documentos"
    SUPABASE_BUCKET_EXPORTS: str = "exportaciones"

    # ─── Mexican Legal Constants ─────────────────────────────
    TASA_TIE_REFERENCIA: float = Field(default=0.1125, gt=0)
    PRECIO_DIESEL_REFERENCIA: float = Field(default=24.50, gt=0)
    # CORREGIDO (contra-auditoría V9): UMBRAL_ADJUDICACION_DIRECTA_OBRA/
    # UMBRAL_INVITACION_TRES_OBRA vivían aquí Y en
    # app/core/constants.py::ConstantesLegales2026 -- dos copias del mismo
    # dato. Verificado con grep en todo el backend: `settings.UMBRAL_*`
    # nunca se lee en ningún lado (el flujo real de umbral de monto es
    # JuridicoService -> MotorJuridico -> umbrales_referencia.py desde
    # F-01). Eliminadas aquí; la copia en constants.py también se
    # eliminó por la misma razón (ver ese archivo).
    DIAS_AGUINALDO_MINIMO: int = Field(default=15, ge=0)
    DIAS_VACACIONES_MINIMO: int = Field(default=12, ge=0)
    PRIMA_VACACIONAL_PCT: float = Field(default=0.25, ge=0, le=1)

    # ─── Feature Flags ───────────────────────────────────────
    FEATURE_BIM_VIEWER: bool = Field(default=True)
    FEATURE_OCR_METRADOS: bool = Field(default=True)
    FEATURE_BLOCKCHAIN_AUDIT: bool = Field(default=False)
    # Tezcatlipoca AI permanece explícitamente deshabilitado hasta que exista
    # un cierre independiente de seguridad, tenancy y validación determinista.
    FEATURE_AI_ASSISTANT: bool = Field(default=False)
    FEATURE_ADVANCED_ANALYTICS: bool = Field(default=False)

    # ─── BIM / IFC ───────────────────────────────────────────
    IFC_MAX_FILE_SIZE_MB: int = Field(default=500, ge=1)
    IFC_PROCESSING_TIMEOUT_SECONDS: int = Field(default=300, ge=30, le=1800)
    IFC_DEDICATED_QUEUE: bool = False
    BIM_STORAGE_PROVIDER: str = Field(default='supabase', pattern=r'^(supabase|filesystem)$')
    BIM_LOCAL_STORAGE_PATH: str = './storage/bim'
    TENDER_SOURCE_MAX_FILE_SIZE_MB: int = Field(default=100, ge=1, le=2048)
    GENERAL_UPLOAD_MAX_FILE_SIZE_MB: int = Field(default=100, ge=1, le=2048)
    CATALOGO_ORIGINALES_DIR: Optional[str] = None
    CERTIFICATE_MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=64)

    # TSA destinations are deployment configuration, never request-controlled
    # network targets. Built-in public TSAs remain available; this list adds
    # explicitly reviewed enterprise endpoints.
    TSA_ALLOWED_URLS: List[str] = Field(default_factory=list)

    # JSON arrays of read-only PEM bundle paths for signing and TSA roots.
    # Empty roots trust no certificate; intermediates never become anchors.
    FIEL_TRUST_ROOT_PATHS: List[str] = Field(default_factory=list)
    FIEL_INTERMEDIATE_CERT_PATHS: List[str] = Field(default_factory=list)
    # Enable only after reviewing OCSP/CRL/AIA egress for the deployment.
    FIEL_ALLOW_REVOCATION_FETCHING: bool = Field(default=False)

    @field_validator("TSA_ALLOWED_URLS", mode="before")
    @classmethod
    def _parse_tsa_allowed_urls(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ─── Monte Carlo ─────────────────────────────────────────
    MONTECARLO_DEFAULT_ITERATIONS: int = Field(default=10_000, ge=100)
    MONTECARLO_MAX_ITERATIONS: int = Field(default=1_000_000, ge=1_000)

    # ─── Notifications ───────────────────────────────────────
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None

    # ─── FSR Sources ─────────────────────────────────────────
    INEGI_PRECIOS_URL: str = "https://www.inegi.org.mx/app/indicesdeprecios/"
    BANXICO_UDIS_URL: str = "https://www.banxico.org.mx/tipcamb/main.do"
    CONASAMI_SALARIOS_URL: str = "https://www.conasami.gob.mx"

    # ─── CORS ────────────────────────────────────────────────
    # BUG ORIGINAL: `allow_origins=["*"] if dev else []` combinado con
    # `allow_credentials=True`. En dev, "*" + credentials fuerza a
    # Starlette a reflejar el Origin de la petición (necesario porque los
    # navegadores rechazan "*" literal junto con credentials) -- funciona,
    # pero de facto acepta CUALQUIER origen con credenciales, lo cual es
    # una superficie CSRF innecesaria incluso en dev. En producción, `[]`
    # bloquea TODO origen -- si el frontend se sirve desde un dominio
    # distinto al del API (el caso típico de una SPA + API separados),
    # ningún request autenticado desde el navegador funcionaría. Se
    # reemplaza por una allowlist explícita y configurable por entorno.
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ─── Frontend (para construir URLs de retorno de pago) ─────
    FRONTEND_URL: str = "http://localhost:5173"

    # ─── Pagos: Mercado Pago (proveedor principal) ─────────────
    # Sin ACCESS_TOKEN el backend arranca igual -- las rutas de pago con
    # MP simplemente responden "proveedor no configurado" en vez de
    # tronar en boot (ver app/integrations/payments/mercadopago_provider.py).
    MERCADOPAGO_ACCESS_TOKEN: Optional[str] = None
    MERCADOPAGO_WEBHOOK_SECRET: Optional[str] = None

    # ─── Pagos: Stripe (proveedor opcional) ────────────────────
    # A propósito NO requerido. Si STRIPE_SECRET_KEY es None (default),
    # el proveedor Stripe se auto-deshabilita: no truena el arranque, ni
    # siquiera si el paquete `stripe` no está instalado (import perezoso
    # y protegido, ver stripe_provider.py). Actívalo con
    # `pip install .[stripe]` + estas variables cuando haga falta.
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        return v.lower()

    @field_validator("SECURITY_PROTECTION_FAILURE_POLICY", mode="before")
    @classmethod
    def _parse_failure_policy(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, FailurePolicy):
            return v
        if isinstance(v, str):
            normalized = v.strip().lower()
            return FailurePolicy(normalized)
        return v

    # SEGURIDAD: docker-compose.yml trae SECRET_KEY=change-me-in-production
    # como default de desarrollo. Hoy ese string en particular ya falla por
    # min_length=32, pero eso es un accidente de longitud, no una regla
    # explícita -- un placeholder de 32+ caracteres pasaría sin avisar.
    # Esto falla el arranque a propósito si ENVIRONMENT=production trae
    # cualquier secreto que se vea como placeholder de desarrollo.
    _INSECURE_SECRET_MARKERS = (
        "change-me", "changeme", "change_me", "changethis",
        "dev-secret", "development", "insecure", "placeholder",
        "your-secret", "secret-key", "example", "test-secret",
    )

    @model_validator(mode="after")
    def _reject_insecure_production_secrets(self) -> "Settings":
        if not self.is_production:
            return self
        lowered = self.SECRET_KEY.lower()
        if any(marker in lowered for marker in self._INSECURE_SECRET_MARKERS):
            raise ValueError(
                "SECRET_KEY se ve como un placeholder de desarrollo "
                f"(coincide con: {[m for m in self._INSECURE_SECRET_MARKERS if m in lowered]}) "
                "pero ENVIRONMENT=production. Genera un secreto real "
                "(ej. `openssl rand -hex 32`) antes de desplegar."
            )
        return self

    @model_validator(mode="after")
    def _apply_security_failure_default(self) -> "Settings":
        if self.SECURITY_PROTECTION_FAILURE_POLICY is None:
            default_policy = (
                FailurePolicy.FAIL_OPEN if self.is_development else FailurePolicy.FAIL_CLOSED
            )
            object.__setattr__(self, "SECURITY_PROTECTION_FAILURE_POLICY", default_policy)
        return self

    @model_validator(mode="after")
    def _reject_insecure_production_runtime(self) -> "Settings":
        if not self.is_production:
            return self

        if self.DEBUG:
            raise ValueError("DEBUG no puede estar habilitado en producción")

        db_url = self.database_async_url.lower()
        if db_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL no puede ser SQLite en producción; usa PostgreSQL/asyncpg")

        if self.database_connection.ssl_mode not in {"verify-ca", "verify-full"}:
            raise ValueError(
                "DATABASE_URL must use verified TLS (DATABASE_SSL_MODE=verify-ca or verify-full)."
            )

        loopback_markers = ("localhost", "127.0.0.1", "::1")
        redis_urls = [str(self.REDIS_URL), str(self.CELERY_BROKER_URL), str(self.CELERY_RESULT_BACKEND)]
        for label, url in zip(("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"), redis_urls):
            lowered = url.lower()
            if any(marker in lowered for marker in loopback_markers):
                raise ValueError(f"{label} no puede apuntar a loopback en producción: {url}")

        if not self.CORS_ALLOWED_ORIGINS:
            raise ValueError("CORS_ALLOWED_ORIGINS no puede estar vacío en producción")

        if any(origin.strip() == "*" for origin in self.CORS_ALLOWED_ORIGINS):
            raise ValueError("CORS_ALLOWED_ORIGINS no puede contener '*' en producción")

        # Hallazgo 2026-08-27: docker-compose.prod.yml declara un servicio
        # `minio` pero no inyecta SUPABASE_URL/SUPABASE_SERVICE_KEY al
        # contenedor `api`/`worker` -- y app/integrations/supabase_storage.py
        # (usado por BIM, documentos, firma, procurement evidence, y los
        # workers de PDF/Excel) no tiene ningún camino de MinIO: si faltan
        # esas dos variables, hoy sólo truena en el primer upload real,
        # como MegalodonException, no al arrancar. Eso pasa el health check
        # y falla en producción con el primer usuario real. No elegí MinIO
        # vs Supabase por el usuario -- Supabase es lo único que el código
        # de storage sabe hablar hoy, así que exigirlo aquí es describir la
        # realidad del código, no una preferencia de infraestructura. Si se
        # decide migrar a MinIO/S3-compatible, este check se actualiza
        # junto con supabase_storage.py, no antes.
        if not self.SUPABASE_URL or not self.SUPABASE_SERVICE_KEY:
            raise ValueError(
                "SUPABASE_URL y SUPABASE_SERVICE_KEY son obligatorios en producción -- "
                "app/integrations/supabase_storage.py no tiene alternativa de storage. "
                "Si docker-compose.prod.yml está declarando MinIO en su lugar, esa "
                "topología no coincide con lo que el código de storage usa; hay que "
                "decidir una autoridad de storage y cablearla end-to-end antes de "
                "desplegar, no dejar que falle en el primer upload real."
            )

        return self

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def security_protection_fail_closed(self) -> bool:
        return self.SECURITY_PROTECTION_FAILURE_POLICY == FailurePolicy.FAIL_CLOSED

    @security_protection_fail_closed.setter
    def security_protection_fail_closed(self, value: bool) -> None:
        object.__setattr__(
            self,
            "SECURITY_PROTECTION_FAILURE_POLICY",
            FailurePolicy.FAIL_CLOSED if value else FailurePolicy.FAIL_OPEN,
        )

    @property
    def database_connection(self):
        """Runtime DML connection with asyncpg-compatible, verified TLS."""
        from app.db.connection import build_database_connection

        return build_database_connection(
            self.DATABASE_URL,
            ssl_mode=self.DATABASE_SSL_MODE,
            ssl_root_cert=self.DATABASE_SSL_ROOT_CERT,
        )

    @property
    def migration_database_connection(self):
        """DDL connection for Alembic; never falls back to DML in production."""
        from app.db.connection import build_database_connection

        if self.is_production:
            if not self.MIGRATION_DATABASE_URL:
                raise ValueError(
                    "MIGRATION_DATABASE_URL is required when Alembic runs in production."
                )
            runtime_user = make_url(self.DATABASE_URL).username
            migration_user = make_url(self.MIGRATION_DATABASE_URL).username
            if not runtime_user or not migration_user or runtime_user == migration_user:
                raise ValueError(
                    "MIGRATION_DATABASE_URL debe usar un rol PostgreSQL distinto al de DATABASE_URL."
                )
            runtime_database = make_url(self.DATABASE_URL).database
            migration_database = make_url(self.MIGRATION_DATABASE_URL).database
            if not runtime_database or runtime_database != migration_database:
                raise ValueError(
                    "MIGRATION_DATABASE_URL debe apuntar a la misma base PostgreSQL que DATABASE_URL."
                )

        connection = build_database_connection(
            self.MIGRATION_DATABASE_URL or self.DATABASE_URL,
            ssl_mode=self.DATABASE_SSL_MODE,
            ssl_root_cert=self.DATABASE_SSL_ROOT_CERT,
        )
        if self.is_production and connection.ssl_mode not in {"verify-ca", "verify-full"}:
            raise ValueError(
                "MIGRATION_DATABASE_URL must use verified TLS (DATABASE_SSL_MODE=verify-ca or verify-full)."
            )
        return connection

    @property
    def database_async_url(self) -> str:
        """Normalized runtime DML URL. Never logs or returns connect credentials separately."""
        return self.database_connection.url

    @property
    def migration_async_url(self) -> str:
        """Normalized DDL URL used only by Alembic."""
        return self.migration_database_connection.url


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuración."""
    return Settings()


settings = get_settings()
