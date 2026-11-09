"""Pre-GO guarantees for the cryptographic audit ledger."""
import pytest
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import MegalodonException
from app.models.audit_ledger import TipoAccion
from app.modules.audit.service import AuditService


@pytest.mark.asyncio
async def test_audit_service_derives_predecessor_and_seals_v2(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    service = AuditService(db_session)

    first = await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="DOCUMENTO",
        entidad_id="doc-pre-go",
        accion=TipoAccion.CREAR,
        descripcion="Creación controlada",
        datos_nuevos={"estado": "BORRADOR"},
    )
    first_hash = first.hash_registro

    second = await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="DOCUMENTO",
        entidad_id="doc-pre-go",
        accion=TipoAccion.APROBAR,
        descripcion="Aprobación controlada",
        datos_anteriores={"estado": "BORRADOR"},
        datos_nuevos={"estado": "APROBADO"},
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert first.hash_version == 2
    assert second.hash_version == 2
    assert second.hash_previo == first_hash
    integrity = await service.verificar_integridad_cadena(
        "DOCUMENTO", "doc-pre-go", tenant.id
    )
    assert integrity == {"valido": True, "registros": 2, "errores": []}


@pytest.mark.asyncio
async def test_stale_audit_predecessor_is_rejected(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    service = AuditService(db_session)
    first = await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="exp-pre-go",
        accion=TipoAccion.CREAR,
    )
    await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="exp-pre-go",
        accion=TipoAccion.MODIFICAR,
    )

    with pytest.raises(MegalodonException) as exc:
        await service.registrar_accion(
            tenant_id=tenant.id,
            user_id=user.id,
            user_email=user.email,
            user_role="admin",
            entidad_tipo="EXPEDIENTE",
            entidad_id="exp-pre-go",
            accion=TipoAccion.APROBAR,
            hash_previo=first.hash_registro,
        )
    assert exc.value.status_code == 409
    await db_session.rollback()


@pytest.mark.asyncio
async def test_postgres_rejects_audit_update_delete_and_truncate(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger contract")

    tenant, user = tenant_a_user
    row = await AuditService(db_session).registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="USUARIO",
        entidad_id=str(user.id),
        accion=TipoAccion.CONSULTAR,
        descripcion="Evidencia inmutable",
    )
    row_id = row.id

    for statement in (
        "UPDATE audit_ledger SET descripcion='alterado' WHERE id=:id",
        "DELETE FROM audit_ledger WHERE id=:id",
        "TRUNCATE audit_ledger",
    ):
        with pytest.raises(DBAPIError, match="bitácora de auditoría es inmutable"):
            await db_session.execute(text(statement), {"id": row_id})
        await db_session.rollback()


@pytest.mark.asyncio
async def test_audit_reports_fail_closed_without_explicit_scope(db_session, tenant_a_user):
    _, user = tenant_a_user
    service = AuditService(db_session)

    with pytest.raises(MegalodonException) as user_report:
        await service.reporte_actividad_usuario(user.id)
    assert user_report.value.status_code == 403

    with pytest.raises(MegalodonException) as system_report:
        await service.reporte_actividad_sistema()
    assert system_report.value.status_code == 403


@pytest.mark.asyncio
async def test_same_entity_id_isolated_between_tenants(
    db_session, tenant_a_user, tenant_b_user
):
    tenant_a, user_a = tenant_a_user
    tenant_b, user_b = tenant_b_user
    service = AuditService(db_session)
    entity_id = "same-external-entity-id"

    for tenant, user, description in (
        (tenant_a, user_a, "Tenant A"),
        (tenant_b, user_b, "Tenant B"),
    ):
        await service.registrar_accion(
            tenant_id=tenant.id,
            user_id=user.id,
            user_email=user.email,
            user_role="admin",
            entidad_tipo="EXPEDIENTE",
            entidad_id=entity_id,
            accion=TipoAccion.CREAR,
            descripcion=description,
        )

    history_a = await service.obtener_historial_expediente(entity_id, tenant_id=tenant_a.id)
    history_b = await service.obtener_historial_expediente(entity_id, tenant_id=tenant_b.id)
    assert [row.descripcion for row in history_a] == ["Tenant A"]
    assert [row.descripcion for row in history_b] == ["Tenant B"]

    integrity_a = await service.verificar_integridad_cadena("EXPEDIENTE", entity_id, tenant_a.id)
    integrity_b = await service.verificar_integridad_cadena("EXPEDIENTE", entity_id, tenant_b.id)
    integrity_global = await service.verificar_integridad_cadena(
        "EXPEDIENTE", entity_id, global_scope=True
    )
    assert integrity_a == {"valido": True, "registros": 1, "errores": []}
    assert integrity_b == {"valido": True, "registros": 1, "errores": []}
    assert integrity_global == {"valido": True, "registros": 2, "errores": []}


@pytest.mark.asyncio
async def test_service_advances_timestamp_when_clock_ties_previous_record(
    db_session, tenant_a_user, monkeypatch
):
    tenant, user = tenant_a_user
    service = AuditService(db_session)
    first = await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="timestamp-monotonic",
        accion=TipoAccion.CREAR,
    )

    import app.modules.audit.service as audit_module

    class FixedClock:
        @staticmethod
        def now(_tz):
            return first.created_at

    monkeypatch.setattr(audit_module, "datetime", FixedClock)
    second = await service.registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="timestamp-monotonic",
        accion=TipoAccion.MODIFICAR,
    )

    assert second.created_at > first.created_at
    assert second.created_at - first.created_at == timedelta(microseconds=1)


@pytest.mark.asyncio
async def test_postgres_rejects_new_legacy_hash_version(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger contract")

    tenant, user = tenant_a_user
    previous = await AuditService(db_session).registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="legacy-version-rejected",
        accion=TipoAccion.CREAR,
    )

    with pytest.raises(DBAPIError, match="Las nuevas entradas deben usar hash_version 2"):
        await db_session.execute(
            text("""
                INSERT INTO audit_ledger (
                    id, tenant_id, user_id, user_email, user_role,
                    entidad_tipo, entidad_id, accion, hash_registro,
                    hash_previo, hash_version, created_at
                ) VALUES (
                    :id, :tenant_id, :user_id, :user_email, :user_role,
                    :entidad_tipo, :entidad_id, :accion, :hash_registro,
                    :hash_previo, :hash_version, :created_at
                )
            """),
            {
                "id": uuid4(),
                "tenant_id": tenant.id,
                "user_id": user.id,
                "user_email": user.email,
                "user_role": "admin",
                "entidad_tipo": "EXPEDIENTE",
                "entidad_id": "legacy-version-rejected",
                "accion": "MODIFICAR",
                "hash_registro": "a" * 64,
                "hash_previo": previous.hash_registro,
                "hash_version": 1,
                "created_at": previous.created_at + timedelta(microseconds=1),
            },
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_postgres_rejects_old_writer_that_omits_hash_version(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL server-default contract")

    tenant, user = tenant_a_user
    tenant_id, user_id, user_email = tenant.id, user.id, user.email
    previous = await AuditService(db_session).registrar_accion(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="old-writer-no-hash-version",
        accion=TipoAccion.CREAR,
    )

    with pytest.raises(DBAPIError, match="Las nuevas entradas deben usar hash_version 2"):
        await db_session.execute(
            text("""
                INSERT INTO audit_ledger (
                    id, tenant_id, user_id, user_email, user_role,
                    entidad_tipo, entidad_id, accion, hash_registro,
                    hash_previo, created_at
                ) VALUES (
                    :id, :tenant_id, :user_id, :user_email, :user_role,
                    :entidad_tipo, :entidad_id, :accion, :hash_registro,
                    :hash_previo, :created_at
                )
            """),
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "user_email": user_email,
                "user_role": "admin",
                "entidad_tipo": "EXPEDIENTE",
                "entidad_id": "old-writer-no-hash-version",
                "accion": "MODIFICAR",
                "hash_registro": "b" * 64,
                "hash_previo": previous.hash_registro,
                "created_at": previous.created_at + timedelta(microseconds=1),
            },
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_postgres_rejects_non_monotonic_audit_timestamp(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL timestamp-chain contract")

    tenant, user = tenant_a_user
    previous = await AuditService(db_session).registrar_accion(
        tenant_id=tenant.id,
        user_id=user.id,
        user_email=user.email,
        user_role="admin",
        entidad_tipo="EXPEDIENTE",
        entidad_id="timestamp-trigger",
        accion=TipoAccion.CREAR,
    )

    with pytest.raises(DBAPIError, match="La marca de tiempo debe avanzar"):
        await db_session.execute(
            text("""
                INSERT INTO audit_ledger (
                    id, tenant_id, user_id, user_email, user_role,
                    entidad_tipo, entidad_id, accion, hash_registro,
                    hash_previo, hash_version, created_at
                ) VALUES (
                    :id, :tenant_id, :user_id, :user_email, :user_role,
                    :entidad_tipo, :entidad_id, :accion, :hash_registro,
                    :hash_previo, :hash_version, :created_at
                )
            """),
            {
                "id": uuid4(),
                "tenant_id": tenant.id,
                "user_id": user.id,
                "user_email": user.email,
                "user_role": "admin",
                "entidad_tipo": "EXPEDIENTE",
                "entidad_id": "timestamp-trigger",
                "accion": "MODIFICAR",
                "hash_registro": "c" * 64,
                "hash_previo": previous.hash_registro,
                "hash_version": 2,
                "created_at": previous.created_at,
            },
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_postgres_preserves_audit_references_on_hard_delete(db_session, tenant_a_user):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL foreign-key retention contract")

    tenant, user = tenant_a_user
    tenant_id, user_id, user_email = tenant.id, user.id, user.email
    await AuditService(db_session).registrar_accion(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        user_role="admin",
        entidad_tipo="USUARIO",
        entidad_id=str(user_id),
        accion=TipoAccion.MODIFICAR,
        descripcion="La referencia debe mantenerse en la bitácora",
    )

    with pytest.raises(DBAPIError):
        await db_session.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
    await db_session.rollback()

    with pytest.raises(DBAPIError):
        await db_session.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant_id})
    await db_session.rollback()

    remaining = await db_session.scalar(
        text("SELECT count(*) FROM audit_ledger WHERE tenant_id=:tenant_id AND user_id=:user_id"),
        {"tenant_id": tenant_id, "user_id": user_id},
    )
    assert remaining == 1
