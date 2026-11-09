# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
ProgramacionService - Gestión de programas de obra con CPM/PERT/EVM.
"""
from datetime import datetime
import math
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.programacion import ProgramaObra, ActividadPrograma, EstadoPrograma
from app.models.expediente import ExpedienteObra
from app.engines.programacion.cpm import (
    MotorCPM, Actividad, TipoActividad, TipoDependencia,
    ResultadoCPM, ResultadoPERT, ResultadoEVM,
)
from app.services.base import BaseService
from app.core.authorization import authorize_by_id
from app.core.errors import MegalodonException, ErrorCode
from app.core.calendar import CalendarioLaboral


class ProgramacionService(BaseService[ProgramaObra]):
    """Servicio de programación de obra con CPM, PERT y EVM."""

    def __init__(self, db: AsyncSession, tenant_id: Optional[UUID | str] = None, *, actor_id: Optional[UUID] = None):
        tenant_uuid = UUID(str(tenant_id)) if tenant_id is not None else None
        super().__init__(ProgramaObra, db, tenant_id=tenant_uuid, tenant_required=True)
        self.calendario = CalendarioLaboral()
        self.actor_id = actor_id

    async def _validar_programa_en_expediente(self, programa_id: UUID, expediente_id: UUID, tenant_id: Optional[UUID | str] = None) -> "ProgramaObra":
        """Verifica que el programa exista y pertenezca al expediente indicado."""
        from sqlalchemy import select as sa_select
        result = await self.db.execute(
            sa_select(ProgramaObra)
            .where(ProgramaObra.id == programa_id)
            .where(ProgramaObra.expediente_id == expediente_id)
            .where(ProgramaObra.tenant_id == self.tenant_id)
            .options(selectinload(ProgramaObra.expediente))
        )
        programa = result.scalar_one_or_none()
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado en el expediente {expediente_id}",
            )
        if tenant_id is not None:
            tenant_id = str(tenant_id)
            # expediente.tenant_id != tenant_id — contrato de aislamiento multi-tenant
            if str(programa.expediente.tenant_id) != tenant_id:
                raise MegalodonException(
                    ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                    f"Programa {programa_id} no encontrado en el expediente {expediente_id}",
                )
        return programa

    async def crear_programa(
        self,
        *,
        expediente_id: UUID,
        nombre: str,
        descripcion: Optional[str] = None,
        fecha_inicio: datetime,
        actividades_data: List[Dict[str, Any]],
        creado_por_id: Optional[UUID] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> ProgramaObra:
        """Crea programa + actividades + CPM como una sola unidad atómica."""
        self.actor_id = self.actor_id or creado_por_id
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        result = await self.db.execute(
            select(ExpedienteObra).where(ExpedienteObra.id == expediente_id)
        )
        expediente = result.scalar_one_or_none()
        if not expediente:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado",
            )

        effective_tenant = tenant_id if tenant_id is not None else self.tenant_id
        effective_tenant = (
            str(effective_tenant) if effective_tenant is not None else None
        )
        if (
            effective_tenant is not None
            and str(expediente.tenant_id) != effective_tenant
        ):
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Expediente {expediente_id} no encontrado en el tenant {effective_tenant}",
            )

        count_result = await self.db.execute(
            select(ProgramaObra).where(
                ProgramaObra.expediente_id == expediente_id
            )
        )
        count = len(count_result.scalars().all()) + 1
        identificador = f"PRO-{expediente.identificador}-{count:03d}"

        programa = ProgramaObra(
            id=uuid4(),
            tenant_id=expediente.tenant_id,
            identificador=identificador,
            nombre=nombre,
            descripcion=descripcion,
            expediente_id=expediente_id,
            fecha_inicio_plan=fecha_inicio,
            estado=EstadoPrograma.PLANIFICADO.value,
            creado_por_id=creado_por_id,
            actualizado_por_id=creado_por_id,
        )

        try:
            self.db.add(programa)
            await self.db.flush()

            for i, act_data in enumerate(actividades_data, 1):
                actividad = ActividadPrograma(
                    id=uuid4(),
                    programa_id=programa.id,
                    identificador=act_data.get("id", f"ACT-{i:03d}"),
                    nombre=act_data["nombre"],
                    descripcion=act_data.get("descripcion", ""),
                    wbs_codigo=act_data.get("wbs_codigo", ""),
                    wbs_nivel=act_data.get("wbs_nivel", 0),
                    duracion=act_data.get("duracion", 0),
                    duracion_optimista=act_data.get("duracion_optimista"),
                    duracion_probable=act_data.get("duracion_probable"),
                    duracion_pesimista=act_data.get("duracion_pesimista"),
                    tipo=act_data.get("tipo", "CONSTRUCCION"),
                    costo_presupuestado=act_data.get(
                        "costo_presupuestado", 0
                    ),
                    costo_real=act_data.get("costo_real", 0),
                    porcentaje_avance=act_data.get(
                        "porcentaje_avance", 0
                    ),
                    predecesoras=act_data.get("predecesoras", []),
                    dependencias_tipo=act_data.get(
                        "dependencias_tipo", {}
                    ),
                    metadatos=act_data.get("metadatos", {}),
                    tenant_id=programa.tenant_id,
                )
                self.db.add(actividad)

            # Flush hace visibles las filas a las consultas del mismo
            # transaction sin publicar un programa parcialmente válido.
            await self.db.flush()

            # Validar y recalcular dentro de la misma transacción. El commit
            # ocurre una sola vez después de que CPM acepta el grafo completo.
            await self.calcular_cpm(
                programa.id,
                expediente_id,
                fecha_inicio,
                tenant_id=tenant_id,
                auto_commit=False,
            )
            await self.db.commit()
            await self.db.refresh(programa)
            return programa
        except Exception:
            await self.db.rollback()
            raise

    async def calcular_cpm(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        fecha_inicio: Optional[datetime] = None,
        tenant_id: Optional[UUID | str] = None,
        *,
        auto_commit: bool = True,
    ) -> ResultadoCPM:
        """Calcula CPM para un programa existente."""
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        # BUG ORIGINAL: expediente_id llegaba como parámetro pero nunca se
        # usaba -- cualquiera que conociera un programa_id podía calcular/leer
        # su CPM pasando CUALQUIER expediente_id en la URL (el query solo
        # filtraba por programa_id). Incluso dentro del mismo tenant, un
        # programa de la Obra A quedaba accesible/mutable vía la ruta de la
        # Obra B. Se valida pertenencia real antes de tocar nada.
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )

        if not fecha_inicio:
            fecha_inicio = programa.fecha_inicio_plan

        # Construir motor CPM
        motor = MotorCPM(self.calendario)

        # Mapear actividades DB a modelo CPM
        actividades_cpm = {}
        for act_db in programa.actividades:
            act = Actividad(
                id=act_db.identificador,
                nombre=act_db.nombre,
                descripcion=act_db.descripcion or "",
                duracion=float(act_db.duracion),
                duracion_optimista=float(act_db.duracion_optimista) if act_db.duracion_optimista else None,
                duracion_probable=float(act_db.duracion_probable) if act_db.duracion_probable else None,
                duracion_pesimista=float(act_db.duracion_pesimista) if act_db.duracion_pesimista else None,
                tipo=TipoActividad(act_db.tipo),
                predecesoras=act_db.predecesoras or [],
                costo_presupuestado=float(act_db.costo_presupuestado),
                costo_real=float(act_db.costo_real),
                porcentaje_avance=float(act_db.porcentaje_avance),
                wbs_nivel=act_db.wbs_nivel,
                wbs_codigo=act_db.wbs_codigo,
            )
            # Mapear dependencias
            for pred in act.predecesoras:
                act.dependencias[pred] = TipoDependencia.FIN_INICIO
            if act_db.dependencias_tipo:
                for pred, tipo in act_db.dependencias_tipo.items():
                    act.dependencias[pred] = TipoDependencia(tipo)

            motor.agregar_actividad(act)
            actividades_cpm[act_db.identificador] = act

        # Calcular sucesoras
        for act in motor.actividades.values():
            for other in motor.actividades.values():
                if act.id in other.predecesoras:
                    act.sucesoras.append(other.id)

        # Ejecutar CPM
        resultado = motor.calcular_cpm(fecha_inicio, usar_calendario=True)

        # Actualizar actividades en DB
        for act_db in programa.actividades:
            act_cpm = actividades_cpm.get(act_db.identificador)
            if act_cpm:
                act_db.inicio_temprano = act_cpm.inicio_temprano
                act_db.fin_temprano = act_cpm.fin_temprano
                act_db.inicio_tardio = act_cpm.inicio_tardio
                act_db.fin_tardio = act_cpm.fin_tardio
                act_db.holgura_total = act_cpm.holgura_total
                act_db.holgura_libre = act_cpm.holgura_libre
                act_db.en_ruta_critica = act_cpm.en_ruta_critica

        # Actualizar programa
        programa.resultado_cpm = resultado.to_dict()
        programa.fecha_fin_plan = resultado.ruta_critica.fecha_fin
        programa.duracion_plan_dias = int(math.ceil(resultado.duracion_total))

        if auto_commit:
            await self.db.commit()
        else:
            await self.db.flush()

        return resultado

    async def calcular_pert(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        fecha_objetivo: Optional[datetime] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> ResultadoPERT:
        """Calcula PERT sin romper el grafo cuando mezcla tareas deterministas."""
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        await self._validar_programa_en_expediente(
            programa_id, expediente_id, tenant_id=tenant_id
        )
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )

        motor = MotorCPM(self.calendario)

        for act_db in programa.actividades:
            optimista = getattr(act_db, "duracion_optimista", None)
            probable = getattr(act_db, "duracion_probable", None)
            pesimista = getattr(act_db, "duracion_pesimista", None)
            act = Actividad(
                id=act_db.identificador,
                nombre=act_db.nombre,
                duracion=float(act_db.duracion),
                duracion_optimista=(
                    float(optimista) if optimista is not None else None
                ),
                duracion_probable=(
                    float(probable) if probable is not None else None
                ),
                duracion_pesimista=(
                    float(pesimista) if pesimista is not None else None
                ),
                predecesoras=list(
                    getattr(act_db, "predecesoras", None) or []
                ),
            )
            tipos = getattr(act_db, "dependencias_tipo", None) or {}
            for pred in act.predecesoras:
                act.dependencias[pred] = TipoDependencia(
                    tipos.get(pred, TipoDependencia.FIN_INICIO.value)
                )
            motor.agregar_actividad(act)

        resultado = motor.calcular_pert(
            programa.fecha_inicio_plan, fecha_objetivo
        )

        programa.resultado_pert = resultado.to_dict()
        await self.db.commit()

        return resultado

    async def calcular_evm(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        fecha_corte: Optional[datetime] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> ResultadoEVM:
        """Calcula EVM (Earned Value Management)."""
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )

        if not fecha_corte:
            fecha_corte = datetime.now()

        motor = MotorCPM(self.calendario)

        for act_db in programa.actividades:
            act = Actividad(
                id=act_db.identificador,
                nombre=act_db.nombre,
                duracion=float(act_db.duracion),
                inicio_temprano=act_db.inicio_temprano,
                fin_temprano=act_db.fin_temprano,
                costo_presupuestado=float(act_db.costo_presupuestado),
                costo_real=float(act_db.costo_real),
                porcentaje_avance=float(act_db.porcentaje_avance),
            )
            motor.agregar_actividad(act)

        resultado = motor.calcular_evm(fecha_corte)

        programa.resultado_evm = resultado.to_dict()
        await self.db.commit()

        return resultado

    async def actualizar_avance(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        actividad_id: str,
        porcentaje: float,
        costo_real: Optional[float] = None,
        tenant_id: Optional[UUID | str] = None,
    ) -> ActividadPrograma:
        """Actualiza avance de una actividad."""
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        result = await self.db.execute(
            select(ActividadPrograma)
            .where(ActividadPrograma.programa_id == programa_id)
            .where(ActividadPrograma.identificador == actividad_id)
        )
        actividad = result.scalar_one_or_none()

        if not actividad:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Actividad {actividad_id} no encontrada en programa {programa_id}",
            )

        actividad.porcentaje_avance = max(0, min(100, porcentaje))
        if costo_real is not None:
            actividad.costo_real = costo_real

        await self.db.commit()
        await self.db.refresh(actividad)

        return actividad

    async def listar_actividades(self, programa_id: UUID, expediente_id: UUID, tenant_id: Optional[UUID | str] = None) -> List[ActividadPrograma]:
        """Actividades completas (predecesoras, tipo, costos) para poblar
        una vista de edición -- exportar_programa da un resumen, no esto."""
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )
        return sorted(programa.actividades, key=lambda a: (a.wbs_codigo or "", a.identificador))

    async def actualizar_actividad(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        actividad_id: str,
        campos: Dict[str, Any],
        tenant_id: Optional[UUID | str] = None,
    ) -> ActividadPrograma:
        """Edita una actividad (duración, predecesoras, tipo, etc.) y
        recalcula el CPM del programa completo, porque cambiar la duración
        o la secuencia de UNA actividad puede mover las fechas, holguras y
        la ruta crítica de todas las demás.

        La validación local rechaza ids inexistentes y auto-referencias.
        La validación de ciclos indirectos y tipos de dependencia vive en
        MotorCPM y se ejecuta antes del único commit, de modo que una edición
        inválida nunca queda persistida aunque el recálculo falle."""
        await authorize_by_id(self.db, self.actor_id, self.tenant_id)
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )

        actividad = next((a for a in programa.actividades if a.identificador == actividad_id), None)
        if not actividad:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Actividad {actividad_id} no encontrada en programa {programa_id}",
            )

        if "predecesoras" in campos and campos["predecesoras"] is not None:
            ids_validos = {a.identificador for a in programa.actividades}
            for pred in campos["predecesoras"]:
                if pred == actividad_id:
                    raise MegalodonException(
                        ErrorCode.VALIDACION_FALLIDA,
                        f"La actividad {actividad_id} no puede ser su propia predecesora",
                    )
                if pred not in ids_validos:
                    raise MegalodonException(
                        ErrorCode.VALIDACION_FALLIDA,
                        f"Predecesora {pred} no existe en este programa",
                    )

        try:
            for campo, valor in campos.items():
                setattr(actividad, campo, valor)

            # Flush publica el cambio solo dentro de esta transacción. CPM ve
            # la edición, pero nada llega a otros consumidores hasta validar
            # el grafo completo y confirmar resultados + actividad juntos.
            await self.db.flush()
            await self.calcular_cpm(
                programa_id,
                expediente_id,
                programa.fecha_inicio_plan,
                tenant_id=tenant_id,
                auto_commit=False,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        await self.db.refresh(actividad)
        return actividad

    async def obtener_gantt(self, programa_id: UUID, expediente_id: UUID, tenant_id: Optional[UUID | str] = None) -> List[Dict[str, Any]]:
        """Obtiene datos para diagrama de Gantt."""
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa or not programa.resultado_cpm:
            return []

        return programa.resultado_cpm.get("gantt", [])

    async def obtener_curva_s(self, programa_id: UUID, expediente_id: UUID, tenant_id: Optional[UUID | str] = None) -> List[Dict[str, Any]]:
        """Obtiene datos para curva S."""
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa or not programa.resultado_cpm:
            return []

        return programa.resultado_cpm.get("curva_s", [])

    async def obtener_ruta_critica(self, programa_id: UUID, expediente_id: UUID, tenant_id: Optional[UUID | str] = None) -> Dict[str, Any]:
        """Obtiene información de la ruta crítica."""
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa or not programa.resultado_cpm:
            return {}

        return programa.resultado_cpm.get("ruta_critica", {})

    async def _get_programa_con_actividades(self, programa_id: UUID) -> Optional[ProgramaObra]:
        """Obtiene programa con sus actividades cargadas."""
        result = await self.db.execute(
            select(ProgramaObra)
            .where(ProgramaObra.id == programa_id)
            .options(selectinload(ProgramaObra.actividades), selectinload(ProgramaObra.expediente))
        )
        return result.scalar_one_or_none()

    async def exportar_programa(
        self,
        programa_id: UUID,
        expediente_id: UUID,
        formato: str = "json",
        tenant_id: Optional[UUID | str] = None,
    ) -> Dict[str, Any]:
        """Exporta programa completo en formato especificado."""
        await self._validar_programa_en_expediente(programa_id, expediente_id, tenant_id=tenant_id)
        programa = await self._get_programa_con_actividades(programa_id)
        if not programa:
            raise MegalodonException(
                ErrorCode.DOCUMENTO_NO_ENCONTRADO,
                f"Programa {programa_id} no encontrado",
            )

        return {
            "programa": {
                "id": str(programa.id),
                "identificador": programa.identificador,
                "nombre": programa.nombre,
                "fecha_inicio_plan": programa.fecha_inicio_plan.isoformat() if programa.fecha_inicio_plan else None,
                "fecha_fin_plan": programa.fecha_fin_plan.isoformat() if programa.fecha_fin_plan else None,
                "duracion_plan_dias": programa.duracion_plan_dias,
                "estado": programa.estado,
            },
            "actividades": [
                {
                    "id": act.identificador,
                    "nombre": act.nombre,
                    "wbs": act.wbs_codigo,
                    "duracion": float(act.duracion),
                    "inicio_temprano": act.inicio_temprano.isoformat() if act.inicio_temprano else None,
                    "fin_temprano": act.fin_temprano.isoformat() if act.fin_temprano else None,
                    "holgura": float(act.holgura_total),
                    "critica": act.en_ruta_critica,
                    "avance": float(act.porcentaje_avance),
                }
                for act in programa.actividades
            ],
            "cpm": programa.resultado_cpm,
            "pert": programa.resultado_pert,
            "evm": programa.resultado_evm,
        }
