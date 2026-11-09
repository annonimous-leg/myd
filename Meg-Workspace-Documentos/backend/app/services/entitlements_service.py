# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Servicio de entitlements: qué plan tiene un tenant AHORA MISMO (no lo
que dice una columna que puede estar desactualizada), cuánto le permite
ese plan, cuánto ha usado, y qué módulos puede abrir.

Principio de seguridad: nunca confiar ciegamente en Tenant.plan como
verdad absoluta -- siempre se compara contra Tenant.plan_vencimiento en
el momento de la consulta. Así, aunque un job periódico que debería
"congelar" el plan vencido no haya corrido todavía, ninguna verificación
de acceso se equivoca (fail-safe hacia FREE, nunca hacia un plan pagado
no vigente).
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.entitlements import (
    PlanLimite, TenantUso, Suscripcion, AppModulo,
    PlanTipo, EstadoModulo, ORDEN_PLAN,
)
from app.models.user import Tenant, UserRole
from app.core.errors import MegalodonException, ErrorCode


# ─── Catálogo por defecto (sembrado, editable después sin redeploy) ────
PLANES_DEFAULT: List[Dict[str, Any]] = [
    {
        "plan": PlanTipo.FREE.value,
        "max_proyectos_activos": 2,
        "max_corridas_costeo_mes": 3,
        "max_consultas_legl_mes": 10,
        "max_catalogos": 1,
        "max_usuarios": 1,
        "permite_api": False,
        "permite_jobs_pesados": False,
        "permite_multi_tenant": False,
        "precio_mensual": 0,
    },
    {
        "plan": PlanTipo.INTERMEDIO.value,
        "max_proyectos_activos": 10,
        "max_corridas_costeo_mes": 25,
        "max_consultas_legl_mes": 50,
        "max_catalogos": 3,
        "max_usuarios": 3,
        "permite_api": False,
        "permite_jobs_pesados": True,
        "permite_multi_tenant": False,
        "precio_mensual": 49,
    },
    {
        "plan": PlanTipo.PRO.value,
        "max_proyectos_activos": 20,
        "max_corridas_costeo_mes": 100,
        "max_consultas_legl_mes": 200,
        "max_catalogos": None,  # varios catálogos sectoriales/regionales, sin tope fijo
        "max_usuarios": 5,
        "permite_api": False,
        "permite_jobs_pesados": True,
        "permite_multi_tenant": False,
        "precio_mensual": 249,
    },
    {
        "plan": PlanTipo.ENTERPRISE.value,
        "max_proyectos_activos": None,
        "max_corridas_costeo_mes": None,
        "max_consultas_legl_mes": None,
        "max_catalogos": None,
        "max_usuarios": None,
        "permite_api": True,
        "permite_jobs_pesados": True,
        "permite_multi_tenant": True,
        "precio_mensual": 699,
    },
]

# Módulos "core" -- negocio real, siempre disponibles en cualquier plan
# (los límites de uso, no el acceso al módulo en sí, es lo que
# diferencia el plan -- ver PLANES_DEFAULT arriba).
_MODULOS_CORE = [
    "proyectos", "topografia", "megalodon-costos", "bim-calculator", "tezcatlipoca-hub",
    "licitaciones-obra", "legl-consultor", "compliance-dashboard",
    "search-global", "transparencia", "consistency-engine", "monte-carlo",
]
# Demo/limitadas -- existen en cualquier plan pero con funcionalidad
# reducida (la reducción específica la implementa cada app; aquí solo
# se registra el estado para que el launcher las pinte como "demo").
_MODULOS_DEMO = [
    "chat", "email-client", "music-player", "rss-reader",
    "chart-maker", "pdf-viewer", "password-manager",
]
# Solo GodAdmin (superadmin) -- observabilidad/soporte de la plataforma,
# nunca para un tenant normal.
_MODULOS_ADMIN_ONLY = ["system-monitor", "api-client"]

MODULOS_DEFAULT: List[Dict[str, Any]] = (
    [
        {"app_id": app_id, "nombre": app_id, "estado": EstadoModulo.CORE.value, "orden": i}
        for i, app_id in enumerate(_MODULOS_CORE)
    ]
    + [
        {"app_id": app_id, "nombre": app_id, "estado": EstadoModulo.DEMO.value, "orden": 100 + i}
        for i, app_id in enumerate(_MODULOS_DEMO)
    ]
    + [
        {
            "app_id": app_id, "nombre": app_id, "estado": EstadoModulo.ADMIN_ONLY.value,
            "requiere_rol": [UserRole.SUPERADMIN.value], "orden": 200 + i,
        }
        for i, app_id in enumerate(_MODULOS_ADMIN_ONLY)
    ]
)


class EntitlementsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Plan efectivo ──────────────────────────────────────────────

    def calcular_plan_efectivo(self, tenant: Tenant) -> str:
        """Nunca confía ciegamente en tenant.plan: si plan_vencimiento ya
        pasó, el plan efectivo es FREE sin importar lo que diga la
        columna (hasta que un job lo actualice físicamente, ver
        revisar_vencimientos_globales)."""
        if tenant.plan == PlanTipo.FREE.value:
            return PlanTipo.FREE.value
        if tenant.plan_vencimiento is None:
            # Un plan pagado sin fecha de vencimiento es una
            # inconsistencia de datos -- se trata como vencido
            # (fail-safe) en vez de asumir "vigente para siempre".
            return PlanTipo.FREE.value
        vencimiento = tenant.plan_vencimiento
        if vencimiento.tzinfo is None:
            vencimiento = vencimiento.replace(tzinfo=timezone.utc)
        if vencimiento < datetime.now(timezone.utc):
            return PlanTipo.FREE.value
        return tenant.plan

    async def obtener_limites(self, plan: str) -> PlanLimite:
        result = await self.db.execute(select(PlanLimite).where(PlanLimite.plan == plan))
        limite = result.scalar_one_or_none()
        if limite is None:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA,
                "Configuración de entitlements incompleta: no existe PlanLimite para el plan efectivo.",
                details={"plan": plan})
        return limite

    async def revisar_vencimientos_globales(self) -> int:
        """Baja a FREE (físicamente, en la columna) los tenants cuyo
        plan_vencimiento ya pasó. Pensado para correr periódicamente
        (Celery beat) -- ver app/workers/. calcular_plan_efectivo() ya
        protege el acceso aunque este job no haya corrido todavía; esto
        solo mantiene la columna consistente para reportes/consultas."""
        ahora = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Tenant).where(
                Tenant.plan != PlanTipo.FREE.value,
                Tenant.plan_vencimiento.isnot(None),
                Tenant.plan_vencimiento < ahora,
            )
        )
        vencidos = result.scalars().all()
        for tenant in vencidos:
            tenant.plan = PlanTipo.FREE.value
        if vencidos:
            await self.db.commit()
        return len(vencidos)

    # ─── Uso / límites ──────────────────────────────────────────────

    @staticmethod
    def _periodo_actual() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def _obtener_o_crear_uso(self, tenant_id: UUID) -> TenantUso:
        periodo = self._periodo_actual()
        result = await self.db.execute(
            select(TenantUso).where(TenantUso.tenant_id == tenant_id, TenantUso.periodo == periodo).with_for_update()
        )
        uso = result.scalar_one_or_none()
        if uso is not None:
            return uso

        # Crear el contador con upsert nativo. Esto evita la carrera clásica
        # "dos workers ven que no existe y ambos intentan insertar" al inicio
        # de mes, que en SaaS podía convertir un uso legítimo en 500/IntegrityError.
        bind = self.db.get_bind()
        dialect = bind.dialect.name
        if dialect == "postgresql":
            stmt = pg_insert(TenantUso).values(tenant_id=tenant_id, periodo=periodo).on_conflict_do_nothing(
                index_elements=["tenant_id", "periodo"]
            )
        elif dialect == "sqlite":
            stmt = sqlite_insert(TenantUso).values(tenant_id=tenant_id, periodo=periodo).on_conflict_do_nothing(
                index_elements=["tenant_id", "periodo"]
            )
        else:
            stmt = None

        if stmt is not None:
            await self.db.execute(stmt)
            await self.db.flush()
        else:
            self.db.add(TenantUso(tenant_id=tenant_id, periodo=periodo))
            await self.db.flush()

        result = await self.db.execute(
            select(TenantUso).where(TenantUso.tenant_id == tenant_id, TenantUso.periodo == periodo).with_for_update()
        )
        uso = result.scalar_one_or_none()
        if uso is None:
            raise RuntimeError("No se pudo crear el contador de uso del tenant.")
        return uso

    async def verificar_y_registrar_uso(
        self, tenant: Tenant, metrica: str, incremento: int = 1, *, auto_commit: bool = True,
    ) -> None:
        """Verifica que el tenant no exceda su límite del plan para
        `metrica` ("corridas_costeo" | "consultas_legl") y, si no lo
        excede, incrementa el contador. Si lo excede, lanza
        MegalodonException con status 402 (Payment Required) -- el
        código HTTP más honesto para "necesitas pagar/mejorar tu plan
        para seguir usando esto", en vez de un 403 genérico."""
        plan = self.calcular_plan_efectivo(tenant)
        limites = await self.obtener_limites(plan)
        campo_limite = f"max_{metrica}_mes" if not metrica.startswith("max_") else metrica
        limite_valor = getattr(limites, campo_limite, None) if limites else None

        uso = await self._obtener_o_crear_uso(tenant.id)
        actual = getattr(uso, metrica, 0)

        if limite_valor is not None and actual + incremento > limite_valor:
            raise MegalodonException(
                ErrorCode.VALIDACION_FALLIDA,
                f"Alcanzaste el límite de tu plan ({plan}): {limite_valor} "
                f"{metrica.replace('_', ' ')} por mes. Mejora tu plan para continuar.",
                status_code=402,
                details={"plan": plan, "metrica": metrica, "limite": limite_valor, "usado": actual},
            )

        setattr(uso, metrica, actual + incremento)
        if auto_commit:
            await self.db.commit()

    async def revertir_uso(self, tenant: Tenant, metrica: str, decremento: int = 1) -> None:
        """Revierte consumo reservado cuando una operación no llegó a encolarse/aceptarse."""
        if decremento <= 0:
            return
        uso = await self._obtener_o_crear_uso(tenant.id)
        actual = getattr(uso, metrica, 0)
        setattr(uso, metrica, max(0, actual - decremento))
        await self.db.commit()

    # ─── Módulos ────────────────────────────────────────────────────

    async def listar_modulos_para(self, tenant: Tenant, rol_usuario: str) -> List[Dict[str, Any]]:
        plan_efectivo = self.calcular_plan_efectivo(tenant)
        orden_tenant = ORDEN_PLAN.get(PlanTipo(plan_efectivo), 0)

        result = await self.db.execute(
            select(AppModulo).where(AppModulo.activo.is_(True)).order_by(AppModulo.orden)
        )
        modulos = result.scalars().all()

        salida = []
        for m in modulos:
            desbloqueado = True
            motivo = None

            if m.requiere_rol and rol_usuario not in m.requiere_rol:
                desbloqueado = False
                motivo = "rol_insuficiente"
            elif m.requiere_plan:
                orden_requerido = ORDEN_PLAN.get(PlanTipo(m.requiere_plan), 0)
                if orden_tenant < orden_requerido:
                    desbloqueado = False
                    motivo = "plan_insuficiente"

            salida.append({
                "app_id": m.app_id,
                "nombre": m.nombre,
                "estado": m.estado,
                "requiere_plan": m.requiere_plan,
                "requiere_rol": m.requiere_rol,
                "desbloqueado": desbloqueado,
                "motivo_bloqueo": motivo,
            })
        return salida

    async def verificar_modulo(self, tenant: Tenant, rol: str, app_id: str) -> None:
        modulos = await self.listar_modulos_para(tenant, rol)
        modulo = next((m for m in modulos if m["app_id"] == app_id), None)
        if modulo is None or not modulo["desbloqueado"]:
            raise MegalodonException(ErrorCode.VALIDACION_FALLIDA,
                "Módulo no disponible para tu rol o plan", status_code=403)

    # ─── Seeding idempotente ────────────────────────────────────────

    async def sembrar_planes_default(self) -> int:
        result = await self.db.execute(select(PlanLimite.plan))
        existentes = {p for (p,) in result.all()}
        creados = 0
        for definicion in PLANES_DEFAULT:
            if definicion["plan"] in existentes:
                continue
            self.db.add(PlanLimite(**definicion))
            creados += 1
        if creados:
            await self.db.commit()
        return creados

    async def sembrar_modulos_default(self) -> int:
        result = await self.db.execute(select(AppModulo.app_id))
        existentes = {a for (a,) in result.all()}
        creados = 0
        for definicion in MODULOS_DEFAULT:
            if definicion["app_id"] in existentes:
                continue
            self.db.add(AppModulo(**definicion))
            creados += 1
        if creados:
            await self.db.commit()
        return creados
