"""Check production Compose interpolation using synthetic values and no Docker daemon."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RUNTIME_SERVICES = ("release-gate", "api", "worker", "ifc-worker", "job-dispatcher", "scheduler")
APP_SERVICES = ("migrate", *RUNTIME_SERVICES)
INTERNAL_SERVICES = ("db", "redis", "minio")
REQUIRED = ("DATABASE_URL", "MIGRATION_DATABASE_URL", "CORS_ALLOWED_ORIGINS", "ENCRYPTION_MASTER_KEY")
PROD_FILE = BACKEND / "docker-compose.prod.yml"
BASE_FILE = BACKEND / "docker-compose.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    # Exclude inherited deployment variables and any developer .env.
    fixture_env = dict(os.environ)
    variable_names = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", PROD_FILE.read_text() + BASE_FILE.read_text()))
    for name in variable_names | {key for key in fixture_env if key.startswith("COMPOSE_")}:
        fixture_env.pop(name, None)
    fixture_env.update({
        "POSTGRES_PASSWORD": "ci-render-password",
        "SECRET_KEY": "a" * 64,
        "ENCRYPTION_MASTER_KEY": "b" * 64,
        "CORS_ALLOWED_ORIGINS": json.dumps(["https://operator.example.invalid"]),
        "SUPABASE_URL": "https://storage.example.invalid",
        "SUPABASE_SERVICE_KEY": "ci-render-service-key",
        "MINIO_ROOT_USER": "ci-render-user",
        "MINIO_ROOT_PASSWORD": "ci-render-minio-password",
        "OTEL_BACKEND_ENDPOINT": "https://telemetry.example.invalid",
        "OTEL_BACKEND_AUTH_HEADER": "",
    })
    version = subprocess.run(
        ["docker", "compose", "version", "--short"],
        check=True, capture_output=True, text=True, env=fixture_env,
    ).stdout.strip()
    parsed = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    require(parsed is not None and tuple(map(int, parsed.groups())) >= (2, 24, 4),
            "Docker Compose >= 2.24.4 is required for !override")

    runtime_url = "postgresql+asyncpg://runtime:ci-only@database.example.invalid:5432/meg"
    migration_url = "postgresql+asyncpg://migrator:ci-only@database.example.invalid:5432/meg"
    external_redis = {
        "REDIS_URL": "rediss://redis.example.invalid:6379/0",
        "CELERY_BROKER_URL": "rediss://redis.example.invalid:6379/1",
        "CELERY_RESULT_BACKEND": "rediss://redis.example.invalid:6379/2",
    }
    layouts = {"standalone": [PROD_FILE], "overlay": [BASE_FILE, PROD_FILE]}
    with tempfile.TemporaryDirectory(prefix="meg-compose-render-") as temporary:
        empty_env = Path(temporary) / "empty.env"
        empty_env.write_text("", encoding="utf-8")
        for layout, files in layouts.items():
            command = ["docker", "compose", "--project-name", "meg-config-ci", "--env-file", str(empty_env)]
            for path in files:
                command.extend(["-f", str(path)])
            command.extend(["config", "--format", "json"])
            for database_case in ("supabase",):
                case_env = dict(fixture_env)
                case_env.update(
                    DATABASE_URL=runtime_url,
                    MIGRATION_DATABASE_URL=migration_url,
                    DATABASE_SSL_MODE="verify-full",
                    **external_redis,
                )
                result = subprocess.run(command, capture_output=True, text=True, env=case_env, cwd=BACKEND)
                require(result.returncode == 0, f"{layout}/{database_case}: Compose render failed")
                services = json.loads(result.stdout)["services"]
                expected_runtime = runtime_url
                expected_migration = migration_url
                require(services["migrate"]["environment"]["DATABASE_URL"] == expected_runtime,
                        f"{layout}/{database_case}: migration service must retain the runtime DML URL")
                require(services["migrate"]["environment"]["MIGRATION_DATABASE_URL"] == expected_migration,
                        f"{layout}/{database_case}: migrate service must receive the separate DDL URL")
                for service in RUNTIME_SERVICES:
                    environment = services[service]["environment"]
                    require(environment["DATABASE_URL"] == expected_runtime,
                            f"{layout}/{database_case}/{service}: wrong runtime database authority")
                    require(environment["DATABASE_SSL_MODE"] == "verify-full",
                            f"{layout}/{database_case}/{service}: verified PostgreSQL TLS was not propagated")
                    require("MIGRATION_DATABASE_URL" not in environment,
                            f"{layout}/{database_case}/{service}: DDL credential leaked to runtime")
                for service in APP_SERVICES:
                    environment = services[service]["environment"]
                    require(json.loads(environment["CORS_ALLOWED_ORIGINS"]) == ["https://operator.example.invalid"],
                            f"{layout}/{database_case}/{service}: CORS JSON was not propagated")
                    require(environment["ENCRYPTION_MASTER_KEY"] == fixture_env["ENCRYPTION_MASTER_KEY"],
                            f"{layout}/{database_case}/{service}: document key was not propagated")
                    require(environment["SECRET_KEY"] != environment["ENCRYPTION_MASTER_KEY"],
                            f"{layout}/{database_case}/{service}: synthetic keys must remain separate")
                    require(environment["BIM_STORAGE_PROVIDER"] == "supabase",
                            f"{layout}/{database_case}/{service}: development storage provider inherited")
                    for key, index in (("REDIS_URL", 0), ("CELERY_BROKER_URL", 1), ("CELERY_RESULT_BACKEND", 2)):
                        require(environment[key] == external_redis[key],
                                f"{layout}/{database_case}/{service}: wrong {key}")
                for service in INTERNAL_SERVICES:
                    require(not services[service].get("ports"),
                            f"{layout}/{database_case}/{service}: internal ports exposed")
                api_ports = services["api"].get("ports", [])
                require(
                    len(api_ports) == 1
                    and api_ports[0].get("host_ip") == "127.0.0.1"
                    and api_ports[0].get("target") == 8000,
                    f"{layout}/{database_case}: API must bind only to host loopback",
                )
                print(f"PASS production Compose {layout}/{database_case}")

            for required in REQUIRED:
                missing_env = dict(case_env)
                missing_env.pop(required)
                result = subprocess.run(command, capture_output=True, text=True, env=missing_env, cwd=BACKEND)
                require(result.returncode != 0 and required in result.stderr,
                        f"{layout}: missing {required} did not fail configuration")
                print(f"PASS production Compose {layout} requires {required}")

    print("Render checks only: provider connectivity, TLS, storage and production acceptance remain unverified.")


if __name__ == "__main__":
    main()
