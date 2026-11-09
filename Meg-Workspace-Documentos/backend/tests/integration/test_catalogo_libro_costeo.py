import csv
import os
import hashlib
from pathlib import Path
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, func, event

from app.models.presupuesto import Presupuesto, Partida
from app.models.catalogo_conceptos import CatalogoFuente, ConceptoCatalogo
from app.services.catalogo_libro import cargar_catalogo, resolver
from app.services.catalogo_conceptos_service import CatalogoConceptosService
from app.services.presupuesto_service import PresupuestoService
from app.schemas.catalogo_conceptos import ConceptoCatalogoCreate, ConceptoCatalogoOut
from app.schemas.costos import ParametrosCosteoInput
from app.core.errors import MegalodonException
from tests.conftest import _login
from tests.integration.test_closure_two_tenants import make_expediente

PARAMS = dict(factor_indirecto=0, factor_utilidad=0, factor_impuesto=0,
              factor_riesgo=0, fuente="CAPTURA_USUARIO", referencia="Sin recargos: prueba")


@pytest.fixture(autouse=True)
def source_catalogue(tmp_path, monkeypatch):
    from app.services import catalogo_libro
    supplied = os.environ.get("MEGALODON_TEST_CATALOGO_REAL")
    path = Path(supplied) if supplied else tmp_path / "catalogo.csv"
    if not supplied:
        # Controlled test input only; production never falls back to this fixture.
        fields = ["modelo_id", "partida_id", "orden", "descripcion", "supuesto", "cantidad",
                  "unidad", "costo_unitario", "importe", "pdf_pagina_global", "necesita_revision"]
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for i, unit in enumerate(["m²", "%", "iva", ""], 1):
                writer.writerow(dict(modelo_id="1", partida_id="1", orden=str(i),
                    descripcion="Plantilla de prueba", supuesto="", cantidad="2", unidad=unit,
                    costo_unitario="12.50", importe="25.01", pdf_pagina_global="1",
                    necesita_revision="False"))
    monkeypatch.setattr(catalogo_libro, "SOURCE", path)
    cargar_catalogo.cache_clear()
    yield path
    cargar_catalogo.cache_clear()


def test_source_catalogue_preserves_values_and_blocks_percentages(source_catalogue):
    items = cargar_catalogo()
    originals = list(csv.DictReader(source_catalogue.open(encoding="utf-8-sig")))
    assert len(items) == len(originals)
    assert [item["original"] for item in items.values()] == originals
    assert {item["sha256"] for item in items.values()} == {
        hashlib.sha256(source_catalogue.read_bytes()).hexdigest()}
    for item in items.values():
        if item["unidad"].lower() in {"%", "iva", ""}:
            with pytest.raises(MegalodonException):
                resolver(item["id"])
    with pytest.raises(MegalodonException):
        resolver("0" * 64)


@pytest.mark.asyncio
async def test_catalogue_to_saved_budget_recalculation_excel_and_tenant_isolation(
        async_client, db_session, tenant_a_user, tenant_b_user):
    tenant, user = tenant_a_user
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.commit()
    from app.models.entitlements import PlanLimite
    if not await db_session.scalar(select(PlanLimite).where(PlanLimite.plan == "FREE")):
        db_session.add(PlanLimite(plan="FREE", max_corridas_costeo_mes=3))
        await db_session.commit()
    headers = await _login(async_client, user.email)
    catalogue = await async_client.get('/api/v1/catalogo-libro?q=Plantilla', headers=headers)
    assert catalogue.status_code == 200, catalogue.text
    item = next(x for x in catalogue.json()["items"] if x["utilizable"])
    base = f'/api/v1/presupuestos/{exp.id}/presupuestos'
    response = await async_client.post(base, headers=headers, json={
        "nombre": "Precio publicado", "parametros_costeo": PARAMS,
        "partidas": [{"numero": 1, "descripcion": "Alterada", "unidad": "falsa",
                      "cantidad": 2, "precio_unitario": 1, "catalogo_libro_id": item["id"]}],
    })
    assert response.status_code == 200, response.text
    budget = response.json()
    expected = Decimal(item["precio_unitario"]) * 2
    assert Decimal(str(budget["monto_total"])) == expected
    assert budget["partidas"][0]["descripcion"] == item["descripcion"]
    assert budget["partidas"][0]["unidad"] == item["unidad"]
    assert budget["metadatos"]["catalogo_libro"]["1"]["sha256"] == item["sha256"]
    saved = await async_client.get(base, headers=headers)
    assert saved.status_code == 200
    assert any(x["id"] == budget["id"] for x in saved.json())
    recalculated = await async_client.post(f'{base}/{budget["id"]}/recalcular', headers=headers)
    assert recalculated.status_code == 200, recalculated.text
    assert Decimal(str(recalculated.json()["monto_total"])) == expected
    excel = await async_client.get(f'{base}/{budget["id"]}/excel', headers=headers)
    assert excel.status_code == 200, excel.text
    workbook = load_workbook(BytesIO(excel.content), data_only=True)
    values = [cell.value for sheet in workbook for row in sheet for cell in row]
    assert item["descripcion"] in values
    assert float(expected) in values
    other_headers = await _login(async_client, tenant_b_user[1].email)
    denied = await async_client.get(base, headers=other_headers)
    assert denied.status_code in (403, 404)


@pytest.mark.asyncio
async def test_budget_failure_does_not_commit_header(db_session, tenant_a_user):
    tenant, user = tenant_a_user
    exp = make_expediente(tenant, user)
    db_session.add(exp)
    await db_session.commit()
    exp_id, tenant_id, user_id = exp.id, tenant.id, user.id
    def fail_insert(*args):
        raise RuntimeError("disk/database failure while writing detail")
    event.listen(Partida, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError):
            await PresupuestoService(db_session, tenant_id).crear_desde_costeo(
                expediente_id=exp_id, nombre="Atomicidad",
                partidas_data=[dict(descripcion="Partida", unidad="m", cantidad=1, precio_unitario=12)],
                parametros_costeo=ParametrosCosteoInput(**PARAMS).to_domain(), creado_por_id=user_id)
        await db_session.rollback()
    finally:
        event.remove(Partida, "before_insert", fail_insert)
    assert await db_session.scalar(select(func.count()).select_from(Presupuesto).where(
        Presupuesto.expediente_id == exp_id)) == 0


@pytest.mark.asyncio
async def test_catalogue_price_without_breakdown_and_update(db_session, tenant_a_user):
    _, user = tenant_a_user
    source = CatalogoFuente(nombre=uuid4().hex, tipo="CUSTOM", vigencia_inicio="2026-01-01",
                            vigencia_fin="2026-12-31")
    db_session.add(source)
    await db_session.flush()
    service = CatalogoConceptosService()
    data = ConceptoCatalogoCreate(fuente_id=source.id, clave="REAL", descripcion="Precio real",
                                 unidad="m", precio_unitario=Decimal("12.50"))
    concept = await service.crear_concepto(db_session, data, user)
    assert ConceptoCatalogoOut.model_validate(concept).id == concept.id
    result = await service.calcular_costo_desglosado(db_session, concept.id, 2, 0)
    assert result["total"] == Decimal("25.00")
    assert result["origen_calculo"] == "PRECIO_CATALOGO"
    updated = await service.actualizar_concepto(db_session, concept.id,
        data.model_copy(update={"descripcion": "Descripción corregida"}), user)
    assert updated.descripcion == "Descripción corregida"


def test_budget_rejects_missing_price_and_excess_quantity_precision():
    from pydantic import ValidationError
    from app.api.v1.presupuestos import PartidaCreate
    with pytest.raises(ValidationError, match="requiere precio"):
        PartidaCreate(numero=1, descripcion="Sin costo", unidad="m", cantidad=1)
    with pytest.raises(ValidationError):
        PartidaCreate(numero=1, descripcion="Precisión no persistible", unidad="m",
                      cantidad="1.00001", precio_unitario=1)


def test_missing_catalogue_reports_unavailable(tmp_path, monkeypatch):
    from app.services import catalogo_libro
    monkeypatch.setattr(catalogo_libro, "SOURCE", tmp_path / "absent.csv")
    cargar_catalogo.cache_clear()
    with pytest.raises(MegalodonException) as exc:
        cargar_catalogo()
    assert exc.value.status_code == 503
