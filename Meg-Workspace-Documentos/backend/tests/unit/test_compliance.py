# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from uuid import uuid4
from app.models.compliance import ReglaCumplimiento, Inconformidad, EstadoInconformidad, TipoSancion
from app.schemas.compliance import ReglaCumplimientoCreate, InconformidadCreate, SancionCreate


class TestReglaCumplimiento:
    def test_crear_regla_minima(self):
        data = ReglaCumplimientoCreate(
            nombre="LAASSP Art. 42",
            tipo_procedimiento="LICITACION_PUBLICA",
            etapa="CONVOCATORIA",
        )
        assert data.nombre == "LAASSP Art. 42"
        assert data.obligatorio is True
        assert data.activa is True  # default

    def test_regla_con_requisitos(self):
        data = ReglaCumplimientoCreate(
            nombre="Garantia de seriedad",
            tipo_procedimiento="LICITACION_PUBLICA",
            etapa="RECEPCION_PROPUESTAS",
            requisitos={"monto_minimo": 0.05, "moneda": "MXN"},
        )
        assert data.requisitos["monto_minimo"] == 0.05

    def test_regla_no_obligatoria(self):
        data = ReglaCumplimientoCreate(
            nombre="Regla opcional",
            tipo_procedimiento="ADJUDICACION_DIRECTA",
            etapa="PLANEACION",
            obligatorio=False,
        )
        assert data.obligatorio is False


class TestInconformidad:
    def test_estado_inicial_registrada(self):
        assert EstadoInconformidad.REGISTRADA == "REGISTRADA"
        assert EstadoInconformidad.EN_ANALISIS == "EN_ANALISIS"
        assert EstadoInconformidad.RESUELTA == "RESUELTA"

    def test_crear_inconformidad_minima(self):
        data = InconformidadCreate(
            expediente_id=str(uuid4()),
            titulo="Falta de publicidad",
            descripcion="No se publico en Compranet",
        )
        assert data.titulo == "Falta de publicidad"
        assert data.licitacion_id is None

    def test_crear_inconformidad_con_licitacion(self):
        data = InconformidadCreate(
            expediente_id=str(uuid4()),
            licitacion_id=str(uuid4()),
            titulo="Irregularidad",
            descripcion="Desc",
            evidencia={"archivos": ["doc1.pdf"]},
        )
        assert data.licitacion_id is not None
        assert "archivos" in data.evidencia


class TestSancion:
    def test_tipos_sancion(self):
        assert TipoSancion.INHABILITACION == "INHABILITACION"
        assert TipoSancion.MULTA == "MULTA"
        assert TipoSancion.AMONESTACION == "AMONESTACION"

    def test_crear_sancion_multa(self):
        data = SancionCreate(
            proveedor_id=str(uuid4()),
            tipo=TipoSancion.MULTA,
            motivo="Incumplimiento de contrato",
            monto_multa=500000.00,
        )
        assert data.tipo == TipoSancion.MULTA
        assert data.monto_multa == 500000.00
