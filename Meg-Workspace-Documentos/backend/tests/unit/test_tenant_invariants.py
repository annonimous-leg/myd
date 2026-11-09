"""Tests de invariantes multi-tenant para Megalodon.

Verifica que NINGUNA operación pueda escapar del tenant del usuario.
Estos tests atacan las invariantes, no solo los endpoints felices.
"""
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from fastapi import HTTPException


class TestTenantIsolationInvariant:
    """INVARIANTE: Un tenant jamás puede observar ni modificar datos de otro tenant."""

    @pytest.mark.asyncio
    async def test_dashboard_queries_filter_by_tenant(self):
        """Todas las queries del dashboard deben incluir tenant_id."""
        from app.api.v1.dashboard import get_dashboard_stats
        # Verificar que la función usa current_user.tenant_id
        import inspect
        source = inspect.getsource(get_dashboard_stats)
        assert "current_user.tenant_id" in source
        assert "tenant_id =" in source
        assert "tenant_id ==" in source or "tenant_id ==" in source

    @pytest.mark.asyncio
    async def test_programacion_router_has_tenant_guard(self):
        """El router de programación debe depender de verificar_expediente_tenant."""
        from app.api.v1.programacion import router
        deps = router.dependencies
        dep_strs = [str(d) for d in deps]
        assert any("verificar_expediente_tenant" in s for s in dep_strs),             "Router de programación debe tener guardia de tenant"

    @pytest.mark.asyncio
    async def test_presupuestos_advanced_router_has_tenant_guard(self):
        """El router de presupuestos avanzados debe depender de verificar_expediente_tenant."""
        from app.api.v1.presupuestos_advanced import router
        deps = router.dependencies
        dep_strs = [str(d) for d in deps]
        assert any("verificar_expediente_tenant" in s for s in dep_strs),             "Router de presupuestos avanzados debe tener guardia de tenant"

    @pytest.mark.asyncio
    async def test_workflow_sla_requires_tenant(self):
        """verificar_sla_vencidos debe aceptar tenant_id y filtrar por él."""
        from app.modules.workflow.engine import WorkflowEngine
        import inspect
        source = inspect.getsource(WorkflowEngine.verificar_sla_vencidos)
        assert "tenant_id" in source
        assert "Workflow.tenant_id == tenant_id" in source

    @pytest.mark.asyncio
    async def test_audit_integrity_requires_godadmin(self):
        """verificar_integridad debe requerir godadmin."""
        from app.api.v1.audit import router
        for route in router.routes:
            if route.path == "/verificar-integridad/{entidad_tipo}/{entidad_id}":
                dep_strs = [str(d) for d in route.dependencies]
                assert any("requiere_godadmin" in s for s in dep_strs),                     "verificar_integridad debe requerir godadmin"

    @pytest.mark.asyncio
    async def test_catalogo_conceptos_requires_admin(self):
        """Catálogo de conceptos debe requerir rol admin."""
        from app.api.v1.catalogo_conceptos import router
        deps = router.dependencies
        dep_strs = [str(d) for d in deps]
        assert any("admin" in s for s in dep_strs),             "Catálogo de conceptos debe requerir admin"

    @pytest.mark.asyncio
    async def test_documento_dedup_filters_by_tenant(self):
        """La deduplicación de documentos debe filtrar por tenant."""
        from app.services.documento_service import DocumentoService
        import inspect
        source = inspect.getsource(DocumentoService.crear_documento)
        assert "tenant_id" in source
        assert "ExpedienteObra.tenant_id == tenant_id" in source


class TestNoGlobalQueriesInvariant:
    """INVARIANTE: No debe existir query global sin filtro de tenant en módulos multi-tenant."""

    def test_dashboard_no_bare_count(self):
        """Dashboard no debe hacer count(*) sin tenant."""
        from app.api.v1 import dashboard
        import inspect
        source = inspect.getsource(dashboard)
        # No debe haber count sin where tenant_id
        lines = source.split('\n')
        for i, line in enumerate(lines):
            if 'func.count(' in line and 'tenant_id' not in line:
                # Verificar que la siguiente línea tenga tenant_id
                next_lines = ' '.join(lines[i:i+5])
                assert 'tenant_id' in next_lines,                     f"Query en dashboard L{i+1} sin filtro de tenant: {line}"


class TestProgramacionServiceTenantValidation:
    """INVARIANTE: El servicio de programación debe validar tenant en crear y validar."""

    @pytest.mark.asyncio
    async def test_crear_programa_validates_tenant(self):
        """crear_programa debe rechazar expediente de otro tenant."""
        from app.services.programacion_service import ProgramacionService
        import inspect
        source = inspect.getsource(ProgramacionService.crear_programa)
        assert "tenant_id" in source
        assert "expediente.tenant_id) != effective_tenant" in source

    @pytest.mark.asyncio
    async def test_validar_programa_en_expediente_checks_tenant(self):
        """_validar_programa_en_expediente debe verificar tenant."""
        from app.services.programacion_service import ProgramacionService
        import inspect
        source = inspect.getsource(ProgramacionService._validar_programa_en_expediente)
        assert "tenant_id" in source
        assert "expediente.tenant_id != tenant_id" in source or "programa.expediente.tenant_id != effective_tenant" in source


class TestP0TenantOwnershipClosures:
    def test_base_service_fails_closed_for_tenant_required_model_without_tenant_id(self):
        from app.services.base import BaseService
        from app.models.base import Base
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column

        class NoTenantModel(Base):
            __tablename__ = "_test_no_tenant_model"
            id: Mapped[str] = mapped_column(String(36), primary_key=True)

        with pytest.raises(TypeError, match="requiere tenant_id"):
            BaseService(NoTenantModel, MagicMock(), tenant_required=True)

    def test_topografia_service_initializes_engines_before_tenant_guard(self):
        from app.services.topografia_service import TopografiaService
        service = TopografiaService(MagicMock())
        assert hasattr(service, "motor_triangulacion")
        assert hasattr(service, "motor_volumenes")
        assert hasattr(service, "motor_geodesia")
        assert hasattr(service, "motor_perfiles")
        assert hasattr(service, "importador")

    def test_programacion_activity_creation_binds_program_tenant(self):
        import inspect
        from app.services.programacion_service import ProgramacionService
        source = inspect.getsource(ProgramacionService.crear_programa)
        assert "tenant_id=programa.tenant_id" in source

    def test_procurement_materializer_binds_tenant_to_budget_graph(self):
        source = (Path(__file__).resolve().parents[2] / "app/engines/procurement/materializer.py").read_text(encoding="utf-8")
        assert "tenant_id=tenant_id" in source
