# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

import pytest
from uuid import uuid4
from app.models.contrato import EstadoContrato, TipoGarantia
from app.schemas.contrato import ContratoCreate, ContratoUpdate, GarantiaCreate, EntregableCreate, ConvenioModificatorioCreate


class TestContratoCreate:
    def test_contrato_valido(self):
        data = ContratoCreate(
            expediente_id=str(uuid4()),
            proveedor_id=str(uuid4()),
            numero_contrato="OC-2026-001",
            objeto="Construccion de puente",
            monto_total=45000000.00,
            plazo_dias=180,
        )
        assert data.monto_total > 0
        assert data.plazo_dias > 0
        assert data.numero_contrato == "OC-2026-001"

    def test_contrato_con_fechas(self):
        data = ContratoCreate(
            expediente_id=str(uuid4()),
            proveedor_id=str(uuid4()),
            numero_contrato="OC-2026-002",
            objeto="Obra",
            monto_total=1000000,
            plazo_dias=90,
            fecha_firma="2026-01-15",
            fecha_inicio="2026-02-01",
            fecha_termino="2026-05-01",
        )
        assert data.fecha_firma == "2026-01-15"

    def test_estado_default_en_firma(self):
        assert EstadoContrato.EN_FIRMA == "EN_FIRMA"
        assert EstadoContrato.VIGENTE == "VIGENTE"
        assert EstadoContrato.TERMINADO == "TERMINADO"


class TestGarantiaCreate:
    def test_garantia_cumplimiento(self):
        data = GarantiaCreate(
            tipo=TipoGarantia.CUMPLIMIENTO,
            monto=2250000.00,
            institucion="Banorte",
            numero_poliza="POL-12345",
        )
        assert data.tipo == TipoGarantia.CUMPLIMIENTO
        assert data.monto == 2250000.00

    def test_garantia_anticipo(self):
        data = GarantiaCreate(
            tipo=TipoGarantia.ANTICIPO,
            monto=1000000.00,
        )
        assert data.tipo == TipoGarantia.ANTICIPO


class TestEntregableCreate:
    def test_entregable_valido(self):
        data = EntregableCreate(
            numero_estimacion=1,
            periodo_inicio="2026-01-01",
            periodo_fin="2026-01-31",
            monto_ejecutado=5000000,
            avance_fisico=25.5,
        )
        assert data.avance_fisico >= 0
        assert data.avance_fisico <= 100


class TestConvenioModificatorioCreate:
    def test_convenio_plazo(self):
        data = ConvenioModificatorioCreate(
            numero="CM-001",
            tipo="PLAZO",
            plazo_anterior=180,
            plazo_nuevo=210,
            justificacion="Retraso por lluvias",
        )
        assert data.tipo == "PLAZO"
        assert data.plazo_nuevo > data.plazo_anterior
