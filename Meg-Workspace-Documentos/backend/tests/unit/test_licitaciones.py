# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from uuid import uuid4
from app.models.licitacion import EstadoLicitacion, TipoProcedimiento
from app.schemas.licitacion import LicitacionCreate, LicitacionUpdate, JuntaAclaracionCreate, ProposicionCreate


class TestLicitacionCreate:
    def test_licitacion_publica(self):
        data = LicitacionCreate(
            expediente_id=str(uuid4()),
            folio="LP-2026-001",
            jurisdiction_code="MX-FED-OBRA",
            tipo_procedimiento=TipoProcedimiento.LICITACION_PUBLICA,
            objeto="Adquisicion de materiales",
            monto_estimado=5000000.00,
            plazo_dias=120,
        )
        assert data.folio == "LP-2026-001"
        assert data.monto_estimado > 0
        assert data.tipo_procedimiento == TipoProcedimiento.LICITACION_PUBLICA

    def test_licitacion_invitacion_tres(self):
        data = LicitacionCreate(
            expediente_id=str(uuid4()),
            folio="IT-2026-001",
            jurisdiction_code="MX-FED-OBRA",
            tipo_procedimiento=TipoProcedimiento.INVITACION_TRES,
            objeto="Servicios",
        )
        assert data.tipo_procedimiento == TipoProcedimiento.INVITACION_TRES

    def test_flujo_estados_completo(self):
        estados = list(EstadoLicitacion)
        assert EstadoLicitacion.PLANEACION in estados
        assert EstadoLicitacion.CONVOCATORIA in estados
        assert EstadoLicitacion.JUNTA_ACLARACIONES in estados
        assert EstadoLicitacion.RECEPCION_PROPUESTAS in estados
        assert EstadoLicitacion.APERTURA in estados
        assert EstadoLicitacion.EVALUACION in estados
        assert EstadoLicitacion.FALLO in estados
        assert EstadoLicitacion.ADJUDICACION in estados
        assert EstadoLicitacion.CONTRATO in estados
        assert EstadoLicitacion.DESIERTA in estados
        assert EstadoLicitacion.CANCELADA in estados


class TestJuntaAclaracionCreate:
    def test_junta_minima(self):
        data = JuntaAclaracionCreate(
            fecha="2026-07-20",
        )
        assert data.fecha == "2026-07-20"

    def test_junta_completa(self):
        data = JuntaAclaracionCreate(
            fecha="2026-07-20",
            acta="Acta de la junta de aclaraciones",
            preguntas_respuestas={
                "preguntas": ["Pregunta 1"],
                "respuestas": ["Respuesta 1"],
            },
            cambios_bases="Se modifico el plazo de 90 a 120 dias",
        )
        assert data.cambios_bases is not None


class TestProposicionCreate:
    def test_proposicion_valida(self):
        data = ProposicionCreate(
            proveedor_id=str(uuid4()),
            monto=4800000.00,
            plazo_dias=110,
        )
        assert data.monto > 0
        assert data.plazo_dias > 0
