# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

from app.models.base import Base

# ─── 0. Platform Core ──────────────────────────────────────
from app.models.user import User, Tenant
from app.models.entidad import Entidad, UnidadAdministrativa
from app.models.audit_ledger import AuditLedger, TipoAccion
from app.models.rules_engine import ReglaNegocio, TipoRegla
from app.models.workflow import (
    TransicionWorkflow, TareaWorkflow, EstadoTarea,
    Workflow, WorkflowPaso, WorkflowTransicion, WorkflowCondicion,
    EstadoWorkflow, EstadoPasoWorkflow,
)

# ─── 1. Catálogos Maestros ─────────────────────────────────
from app.models.proveedor import Proveedor, RepresentanteLegal, TipoPersona, EstadoProveedor
from app.models.catalogo_procedimiento import CatalogoProcedimiento
from app.models.catalogo_juridico import CatalogoJuridico

# ─── 2. Expediente / Case Management ───────────────────────
from app.models.expediente import ExpedienteObra, Documento
from app.models.planeacion import PlaneacionExpediente

# ─── 3. Documento / CDE ────────────────────────────────────
from app.models.documento import DocumentoCDE, EstadoDocumento, TipoDocumento

# ─── 4. Licitaciones ───────────────────────────────────────
from app.models.licitacion import (
    Licitacion, JuntaAclaracion, Proposicion,
    TipoProcedimiento, EstadoLicitacion
)

# ─── 5. Contratos ──────────────────────────────────────────
from app.models.contrato import (
    Contrato, ConvenioModificatorio, GarantiaContrato, EntregableContrato,
    EstadoContrato, TipoGarantia
)

# ─── 6. Compliance ─────────────────────────────────────────
from app.models.compliance import (
    ReglaCumplimiento, Inconformidad, Sancion,
    EstadoInconformidad, TipoSancion
)

# ─── 7. BIM ────────────────────────────────────────────────
from app.models.bim import ModeloBIM, ElementoBIM, AnalisisClash, ClashResult, DibujoBIM

# ─── 8. Costos / APU / Presupuesto ─────────────────────────
from app.models.presupuesto import Presupuesto, Partida, Concepto, Insumo
from app.models.catalogo_apu import CatalogoAPU, PrecioUnitarioAsignado, TipoConceptoAPU, UnidadMedida
from app.models.catalogo_importacion import CatalogoImportacion, CatalogoRegistro, EstimacionParametrica
from app.models.catalogo_conceptos import (
    CatalogoFuente, ConceptoCatalogo, InsumoCatalogo, TipoCatalogo
)
from app.models.indices_costos import SerieIndiceCosto, ObservacionIndiceCosto, VinculoIndiceInsumo, RetiroIndiceCosto, CargaIndiceCosto

# ─── 9. Programación ───────────────────────────────────────
from app.models.programacion import ProgramaObra, ActividadPrograma

# ─── 10. Topografía ────────────────────────────────────────
from app.models.topografia import (
    Levantamiento, PuntoTopografico, SuperficieTIN, CalculoVolumen
)

# ─── 11. Validadores ───────────────────────────────────────
from app.models.validador import ValidacionPropuesta, ValidacionExpediente, CheckValidacion

# ─── 12. Notificaciones ─────────────────────────────────────
from app.models.notifications import NotificationLog

# ─── 13. Entitlements (planes, límites, uso, suscripciones) ─
from app.models.montecarlo import MonteCarloRun, EstadoMonteCarlo
from app.models.ocr_job import OCRJob, OCRJobStatus

from app.models.procurement import (
    TenderPackage, TenderRevision, TenderDocument, TenderDocumentRevision, TenderLicitacionBridge, JurisdictionProfile, JurisdictionInheritance, ProcedureThreshold, LegalSource, LegalRule, TenderRuleDefinition,
    TenderRequirement, TenderEvidence, TenderEvidenceLink, TenderArtifact, TenderDependency,
    TenderValidationRun, TenderValidationEvidenceLink, TenderApproval, SubmissionPackage, TenderState, RequirementCategory,
    RequirementStatus, EvidenceKind, ArtifactStatus, ValidationSeverity, ValidationStatus,
    PreparationRunStatus, PreparationStageStatus, TenderPreparationRun, TenderPreparationStageRun,
)

from app.models.procurement_jobs import ProcurementJob, ProcurementIdempotency, ProcurementStorageIntent

from app.models.entitlements import (
    PlanLimite, TenantUso, Suscripcion, AppModulo,
    PlanTipo, EstadoSuscripcion, ProveedorPago, EstadoModulo,
)

from app.models.process_job import TrabajoProceso
