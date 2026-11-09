# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Schemas Pydantic para toda la API.
"""
from app.schemas.common import (
    PaginationParams, PaginatedResponse, FilterParams,
    MessageResponse, HealthCheck
)
from app.schemas.auth import (
    Token, TokenPayload, UserOut, UserUpdate,
    RefreshRequest, LoginRequest
)
from app.schemas.expediente import (
    ExpedienteCreate, ExpedienteUpdate, ExpedienteOut, ExpedienteList
)
from app.schemas.documento import (
    DocumentoCreate, DocumentoUpdate, DocumentoOut, DocumentoList
)
# app.schemas.presupuesto (PresupuestoOut/PresupuestoCreate/etc.) NO se
# reexporta aquí a propósito: es un schema obsoleto que no coincide con
# el modelo real de Presupuesto (le faltan factor_indirecto/monto_directo/
# partidas y sobran indirectos_pct/financiamiento_pct/utilidad_pct/
# cargo_adicional_pct, que no existen en app.models.presupuesto.Presupuesto).
# El schema realmente en uso es el PresupuestoOut definido localmente en
# app/api/v1/presupuestos.py. Verificado 2026-09-14: nada en el backend
# importaba estos nombres desde app.schemas -- era código muerto que
# aparentaba ser el contrato activo. Se deja app/schemas/presupuesto.py
# en disco sin tocar (por si algo externo al backend lo referenciara) pero
# ya no se carga desde aquí.
from app.schemas.bim import (
    ModeloBIMCreate, ModeloBIMOut, ClashDetectionRequest, ClashResultOut
)
from app.schemas.programacion import (
    ProgramaCreate, ProgramaOut, ActividadCreate, AvanceUpdate
)
from app.schemas.topografia import (
    LevantamientoCreate, LevantamientoOut, PuntoCreate, VolumenRequest
)
from app.schemas.catalogo_apu import (
    CatalogoAPUCreate, CatalogoAPUOut, CatalogoAPUList
)
from app.schemas.dashboard import (
    DashboardStats, KPIData, DashboardResponse
)
from app.schemas.licitacion import (
    LicitacionCreate, LicitacionUpdate, LicitacionOut, LicitacionList,
    JuntaAclaracionCreate, ProposicionCreate
)
from app.schemas.contrato import (
    ContratoCreate, ContratoUpdate, ContratoOut, ContratoList,
    ConvenioModificatorioCreate, GarantiaCreate, EntregableCreate
)
from app.schemas.compliance import (
    ReglaCumplimientoCreate, InconformidadCreate, InconformidadUpdate,
    SancionCreate, ComplianceOut
)
from app.schemas.catalogo_conceptos import (
    CatalogoFuenteCreate, ConceptoCatalogoCreate, ConceptoCatalogoOut,
    ConceptoCatalogoList, InsumoCatalogoCreate, InsumoCatalogoOut
)
from app.schemas.transparencia import (
    ExpedientePublico, DatasetExport
)
