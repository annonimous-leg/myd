"""CI smoke over a real Uvicorn process, with migrated PostGIS and Redis.

This command creates synthetic identities only in disposable GitHub Actions
staging infrastructure. It never seeds a deployed server or uses ASGI overrides.
"""
import asyncio
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import time
from uuid import uuid4

import httpx


async def seed_identities():
    # Import the real application so all related ORM models are registered.
    from app.main import app  # noqa: F401
    from app.models.base import AsyncSessionLocal, engine
    from app.models.user import Tenant, User, UserRole
    from app.services.auth_service import AuthService
    from sqlalchemy import text
    password = uuid4().hex
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="CI runtime smoke", slug=f"ci-smoke-{uuid4().hex}", is_active=True)
        db.add(tenant)
        await db.flush()
        hashed = AuthService(db).hash_password(password)
        admin = User(email=f"{uuid4().hex}@smoke.local", full_name="CI administrator",
                     tenant_id=tenant.id, role=UserRole.ADMIN, is_active=True,
                     hashed_password=hashed)
        member = User(email=f"{uuid4().hex}@smoke.local", full_name="CI member",
                      tenant_id=tenant.id, role=UserRole.TECNICO, is_active=True,
                      hashed_password=hashed)
        db.add_all([admin, member])
        await db.commit()
        result = {"admin_email": admin.email, "member_email": member.email,
                  "member_id": str(member.id), "password": password}
    # Separate runtime credentials have DML permissions but cannot alter tables.
    role, role_password = f"ci_runtime_{uuid4().hex}", uuid4().hex
    async with engine.begin() as connection:
        await connection.execute(text(f'CREATE ROLE "{role}" LOGIN PASSWORD \'{role_password}\''))
        await connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        await connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"'))
        await connection.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
    result["runtime_database_url"] = engine.url.set(username=role, password=role_password).render_as_string(hide_password=False)
    await engine.dispose()
    return result


def expected(response, status, check):
    if response.status_code != status:
        raise RuntimeError(f"{check}: expected HTTP {status}, received {response.status_code}")
    return response


def main():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("ENVIRONMENT") != "staging":
        raise SystemExit("This smoke seeds test identities and runs only in disposable CI staging.")
    identities = asyncio.run(seed_identities())
    checks = []
    log_path = Path("runtime-smoke-server.log")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        env = dict(os.environ)
        env["DATABASE_URL"] = identities["runtime_database_url"]
        env["TEZCATLIPOCA_DATABASE_URL"] = identities["runtime_database_url"]
        env["CORS_ALLOWED_ORIGINS"] = json.dumps([origin])
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--fd", str(listener.fileno()), "--lifespan", "on",
                 "--no-access-log", "--log-level", "info"],
                env=env, pass_fds=(listener.fileno(),),
                stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                with (
                    httpx.Client(base_url=origin, timeout=5, trust_env=False) as client,
                    httpx.Client(base_url=origin, timeout=5, trust_env=False) as sdk,
                ):
                    deadline = time.monotonic() + 90
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Uvicorn stopped before completing startup")
                        try:
                            health = client.get("/health", timeout=1)
                            if health.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if time.monotonic() > deadline:
                            raise RuntimeError("Uvicorn lifespan did not finish within 90 seconds")
                        time.sleep(0.25)
                    assert health.json()["status"] == "healthy"
                    checks.append("Uvicorn lifespan and HTTP health")
                    ready = expected(client.get("/ready"), 200, "Readiness").json()
                    assert ready["ready"] and ready["database"] and ready["redis"], "Core dependencies not ready"
                    checks.append("Migrated PostGIS and real Redis readiness")
                    member_login = expected(sdk.post("/api/v1/auth/login", data={
                        "username": identities["member_email"], "password": identities["password"],
                    }), 200, "Member login").json()
                    member_header = {"Authorization": f"Bearer {member_login['access_token']}"}
                    assert not sdk.cookies, "SDK login must not create ambient browser credentials"
                    expected(sdk.get("/api/v1/auth/me", headers=member_header), 200, "Member identity")
                    checks.append("SDK login and authenticated HTTP identity")
                    browser = expected(client.post("/api/v1/auth/session/login", data={
                        "username": identities["admin_email"], "password": identities["password"],
                    }, headers={"Origin": origin}), 200, "Browser login")
                    assert set(browser.json()) == {"expires_in"}
                    assert all("httponly" in c.lower() for c in browser.headers.get_list("set-cookie"))
                    checks.append("Browser login keeps credentials in HttpOnly cookies")
                    users = expected(client.get("/api/v1/users"), 200, "Tenant users").json()
                    assert len(users) == 2 and identities["member_id"] in {u["id"] for u in users}
                    path = f"/api/v1/users/{identities['member_id']}"
                    body = {"role": "lector", "reason": "Runtime CI approval"}
                    expected(client.patch(path, json=body,
                                          headers={"Origin": "https://attacker.invalid"}), 403, "Hostile origin")
                    changed = expected(client.patch(path, json=body, headers={"Origin": origin}),
                                       200, "Authoritative identity change").json()
                    assert changed["role"] == "lector"
                    expected(sdk.get("/api/v1/auth/me", headers=member_header), 401, "Invalidated access")
                    expected(sdk.post("/api/v1/auth/refresh", json={
                        "refresh_token": member_login["refresh_token"]}), 401, "Invalidated refresh")
                    checks.append("Tenant IAM change, origin protection and access/refresh invalidation")
                    report = {"passed": checks, "transport": "real TCP HTTP",
                              "lifespan": "on", "database_role": "runtime DML without schema ownership", "fixtures": "synthetic CI identities",
                              "optional_tezcatlipoca": ready["optional_dependencies"]["tezcatlipoca"],
                              "production_deployment_certified": False}
            finally:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                    raise RuntimeError("Uvicorn shutdown exceeded 20 seconds")
            shutdown_log = log_path.read_text(errors="replace")
            # Uvicorn 0.50.1 re-raises the captured SIGTERM after graceful exit.
            # Exit status alone cannot establish whether lifespan cleanup ran.
            if process.returncode not in (0, -signal.SIGTERM) or (
                "Application shutdown complete" not in shutdown_log
                or "megalodon_shutdown" not in shutdown_log
            ):
                raise RuntimeError(f"Uvicorn lifecycle cleanup did not complete: {process.returncode}")
    checks.append("Graceful Uvicorn shutdown")
    Path("runtime-smoke-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
