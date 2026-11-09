# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Modelos BIM: modelo IFC subido y elementos cuantificados extraídos de él.

Diseño inspirado en el schema de dominio más completo que encontramos en
app_quitar_a_kimi (modelosBim/elementosBim), adaptado a SQLAlchemy 2.0 async
y a las convenciones ya usadas en el resto del backend (UUID como PK,
Decimal para cantidades monetarias/físicas).

La pieza clave es ElementoBIM.partida_id: es el puente real BIM→presupuesto
que faltaba (el motor_bim.py anterior no persistía nada, era 100% stateless).
"""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, String, Numeric, Integer, JSON, DateTime, func, UniqueConstraint, ForeignKeyConstraint
from app.db.types import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, AuditMixin, TenantMixin, EstadoProceso

# RESTAURACIÓN multi-tenant (FASE1): ModeloBIM, AnalisisClash y
# GeneracionBIM4D5D son las 3 raíces de agregado de este módulo (igual
# que ExpedienteObra/CatalogoAPU en el resto del sistema, mismo criterio:
# llevan AuditMixin => llevan TenantMixin). ElementoBIM, ClashResult y
# ElemementoBIMActividad son entidades hijas insertadas en lote (sin
# AuditMixin, ver convención abajo) y se quedan escaladas por FK a su
# raíz -- mismo patrón que Partida/Concepto bajo Presupuesto o
# ActividadPrograma bajo ProgramaObra, ninguno de los cuales tiene
# tenant_id propio tampoco.


class FuenteCantidad(str, PyEnum):
    """De dónde salió un volumen/área: del IFC (quantity set, confiable) o
    calculada por nosotros desde la malla (fallback, aproximada)."""
    QTO_IFC = "QTO_IFC"
    GEOMETRIA_CALCULADA = "GEOMETRIA_CALCULADA"
    NO_DISPONIBLE = "NO_DISPONIBLE"


class ModeloBIM(Base, UUIDMixin, TenantMixin, AuditMixin):
    __tablename__ = "modelos_bim"

    expediente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identificador: Mapped[str] = mapped_column(String(100), unique=False, nullable=False)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    ruta_archivo: Mapped[str] = mapped_column(String(1000), nullable=False)
    version_ifc: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tamano_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_elementos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    niveles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # nombres ordenados por elevación
    estado_procesamiento: Mapped[str] = mapped_column(
        String(20), default=EstadoProceso.PENDIENTE.value, nullable=False, index=True
    )
    error_procesamiento: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    unidades_ifc: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ej. "METRE", "MILLIMETRE"
    # created_at/updated_at ya vienen de Base -- antes se redeclaraban
    # aquí de forma redundante (mismo default, mismo tipo).

    elementos: Mapped[list["ElementoBIM"]] = relationship(
        "ElementoBIM", back_populates="modelo", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("expediente_id", "identificador", name="uq_modelobim_expediente_identificador"),
        ForeignKeyConstraint(["tenant_id", "expediente_id"],
            ["expedientes_obra.tenant_id", "expedientes_obra.id"], name="fk_modelobim_tenant_expediente"),
    )


class ElementoBIM(Base, UUIDMixin):
    __tablename__ = "elementos_bim"

    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    global_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # IFC GlobalId (GUID)
    express_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # IfcWall, IfcSlab, etc.
    nombre: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Cantidades físicas. Nullable porque no todo elemento tiene las 3.
    volumen: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    area: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    longitud: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    unidad: Mapped[str] = mapped_column(String(20), default="m", nullable=False)

    # De dónde salió cada cantidad: importa para saber cuánto confiar en
    # ella antes de mandarla a costeo (ver FuenteCantidad arriba).
    fuente_volumen: Mapped[str] = mapped_column(String(30), default=FuenteCantidad.NO_DISPONIBLE.value)
    fuente_area: Mapped[str] = mapped_column(String(30), default=FuenteCantidad.NO_DISPONIBLE.value)

    sistema_constructivo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    nivel: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)

    # Agrupación de trabajo para 4D, independiente de `nivel`. `nivel`
    # viene fijo del IFC (el building storey); `zona_4d` la puede ajustar
    # el usuario (endpoint /bim/.../zonas-4d) cuando la secuencia
    # constructiva real no coincide 1:1 con la planta -- ej. una zona que
    # cruza dos niveles, o un nivel que se divide en dos frentes de
    # trabajo. Si no se asigna, BIMService.generar_actividades_4d cae de
    # vuelta a `nivel`.
    zona_4d: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    bbox: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [minx,miny,minz,maxx,maxy,maxz]
    propiedades: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # psets completos, para auditoría

    # Malla triangulada para render en el frontend (Three.js). Se guarda
    # como arrays planos [x1,y1,z1,x2,y2,z2,...] / [i1,i2,i3,...] listos
    # para BufferGeometry. Puede ser null si el elemento no tiene
    # representación geométrica (ej. IfcSpace lógico sin geometría).
    malla_vertices: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    malla_caras: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Puente BIM -> presupuesto. Null hasta que alguien lo mapea a una
    # partida real (endpoint /bim/.../mapear-partidas).
    partida_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("partidas.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (UniqueConstraint("modelo_id", "global_id", name="uq_elementobim_modelo_global"),)

    modelo: Mapped["ModeloBIM"] = relationship("ModeloBIM", back_populates="elementos")


# Antes era un enum propio (EN_PROCESO/COMPLETADO/ERROR) casi idéntico a
# EstadoProcesamientoBIM (PENDIENTE/EN_PROCESO/PROCESADO/ERROR) con
# nombres de valor distintos para lo mismo. Se unifica en EstadoProceso.
EstadoAnalisisClash = EstadoProceso


class SeveridadClash(str, PyEnum):
    """DURO: las mallas se traslapan de verdad (distancia == 0, test
    exacto Möller-Trumbore). BLANDO: no se traslapan pero están más
    cerca que la tolerancia configurada -- útil para reglas de
    clearance (ej. ducto vs estructura) que no requieren traslape
    real."""
    DURO = "DURO"
    BLANDO = "BLANDO"


class EstadoClash(str, PyEnum):
    NUEVO = "NUEVO"
    REVISADO = "REVISADO"
    RESUELTO = "RESUELTO"
    IGNORADO = "IGNORADO"


class AnalisisClash(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Una corrida de clash detection sobre un ModeloBIM. Header con los
    parámetros usados y el resumen -- el detalle por par vive en
    ClashResult (ver abajo). Mismo espíritu de auditoría que
    ValidacionPropuesta.bitacora_evaluacion, pero aquí cada resultado
    necesita su propio ciclo de vida (NUEVO/REVISADO/RESUELTO), así que
    se modela como filas propias en vez de un solo JSON."""
    __tablename__ = "analisis_clash"

    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tolerancia_m: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoProceso.PENDIENTE.value, nullable=False, index=True)
    # FIX P0 auditoría BIM 2026-09-14 (clash async): antes ejecutar_analisis()
    # recibía tipos_incluidos/excluidos como argumentos de función y los
    # usaba en el momento, todo dentro del mismo request síncrono -- no
    # había necesidad de persistirlos. Ahora que el cómputo se mueve a un
    # worker Celery que solo recibe analisis_id, estos filtros tienen que
    # sobrevivir entre el request que crea el AnalisisClash (PENDIENTE) y
    # el worker que lo ejecuta después.
    tipos_incluidos: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tipos_excluidos: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    num_pares_evaluados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_clashes_duros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_clashes_blandos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tiempo_calculo_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    # created_at/updated_at ya vienen de Base.

    resultados: Mapped[list["ClashResult"]] = relationship(
        "ClashResult", back_populates="analisis", cascade="all, delete-orphan"
    )


class ClashResult(Base, UUIDMixin):
    """Un par de elementos en conflicto, con la geometría involucrada
    lista para resaltar en el visor 3D.

    volumen_aproximado_m3 NO es un booleano exacto de las mallas -- es el
    volumen de la intersección de los dos AABB de los elementos (cota
    superior simple). Ver docstring de motor_clash.py."""
    __tablename__ = "clash_resultados"

    analisis_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("analisis_clash.id", ondelete="CASCADE"), nullable=False, index=True
    )
    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    elemento_a_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("elementos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    elemento_b_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("elementos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_a: Mapped[str] = mapped_column(String(100), nullable=False)  # denormalizado, evita joins para listar/filtrar
    tipo_b: Mapped[str] = mapped_column(String(100), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # DURO | BLANDO
    distancia_m: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    volumen_aproximado_m3: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    punto_cercano_a: Mapped[list] = mapped_column(JSON, nullable=False)  # [x,y,z]
    punto_cercano_b: Mapped[list] = mapped_column(JSON, nullable=False)  # [x,y,z]
    # Triángulos involucrados en el conflicto, hasta motor_clash.MAX_TRIANGULOS_REPORTADOS
    # por lado -- [[x,y,z]x3, ...] listos para resaltarse en Three.js sin
    # tener que volver a pedir la malla completa del elemento.
    triangulos_a: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    triangulos_b: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoClash.NUEVO.value, nullable=False, index=True)
    # created_at/updated_at ya vienen de Base.

    analisis: Mapped["AnalisisClash"] = relationship("AnalisisClash", back_populates="resultados")


class GeneracionBIM4D5D(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Una corrida de generación de cronograma 4D a partir de un modelo
    BIM ya cuantificado. Agregado raíz (acción explícita de un usuario:
    "generar 4D desde este modelo"), por eso AuditMixin -- a diferencia
    de ElementoBIM o ElementoBIMActividad, que son entidades hijas
    insertadas en lote.

    Se encola a Celery (BIMService.generar_actividades_4d corriendo
    dentro de workers/bim_tasks.py:generar_4d5d_desde_bim) porque
    agrupar/crear actividades para un modelo con miles de elementos no
    es instantáneo. El frontend hace polling a este registro -- mismo
    patrón que ModeloBIM.estado_procesamiento -- en vez de depender del
    WebSocket genérico de progreso (que es best-effort y no sobrevive un
    restart del proceso API).
    """
    __tablename__ = "generaciones_bim_4d5d"

    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modelos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expediente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Null hasta que la generación termina bien y de verdad existe un
    # ProgramaObra que apuntarle.
    programa_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("programas_obra.id", ondelete="SET NULL"), nullable=True
    )
    estado: Mapped[str] = mapped_column(String(50), default=EstadoProceso.PENDIENTE.value, nullable=False, index=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Cómo se agruparon los elementos: "zona_4d" (si al menos un elemento
    # tenía zona_4d asignada) o "nivel" (fallback). Queda registrado para
    # que quede claro después por qué el cronograma quedó dividido como
    # quedó -- no es una decisión "inteligente", es la regla documentada.
    agrupar_por: Mapped[str] = mapped_column(String(20), default="zona_4d", nullable=False)

    # Duración inicial configurable por actividad generada, en días.
    # Es una entrada de negocio explícita y ajustable por el planificador;
    # no representa una duración calculada automáticamente.
    # origen señala como limitación de Bexel Manager (duraciones
    # genéricas de 5 días que el especialista debe ajustar). No se
    # inventa una duración "inteligente" por tipo de elemento: sería una
    # falsa precisión.
    dias_por_defecto: Mapped[float] = mapped_column(Numeric(8, 2), default=5.0, nullable=False)

    num_actividades_generadas: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ElementoBIMActividad(Base, UUIDMixin):
    """Puente muchos-a-muchos entre ElementoBIM y ActividadPrograma (4D).

    Entidad hija insertada en lote por
    BIMService.generar_actividades_4d -- sin AuditMixin, misma
    convención que ElementoBIM/ClashResult (ver app/models/base.py). Una
    actividad generada agrupa N elementos; el mismo elemento podría en
    principio quedar en más de una actividad (ej. si se regenera el 4D
    con una agrupación distinta y se decide no borrar la anterior), por
    eso es M:N y no una FK simple en ElementoBIM.
    """
    __tablename__ = "elemento_bim_actividad"

    elemento_bim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("elementos_bim.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actividad_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("actividades_programa.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint("elemento_bim_id", "actividad_id", name="uq_elemento_bim_actividad"),
    )


class DibujoBIM(Base, UUIDMixin, TenantMixin, AuditMixin):
    """Request and vector artifacts generated from one immutable IFC revision."""
    __tablename__ = "dibujos_bim"

    modelo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("modelos_bim.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    expediente_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expedientes_obra.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    parametros: Mapped[dict] = mapped_column(JSON, nullable=False)
    formatos: Mapped[list] = mapped_column(JSON, nullable=False)
    permitir_geometria_parcial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default=EstadoProceso.PENDIENTE.value, nullable=False, index=True)
    error: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    source_model_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_num_elementos: Mapped[int] = mapped_column(Integer, nullable=False)
    source_geometry_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    elementos_fuente: Mapped[int] = mapped_column(Integer, nullable=False)
    elementos_con_malla: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    elementos_sin_malla: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    ruta_svg: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    ruta_dxf: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    ruta_pdf: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    sha256_svg: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sha256_dxf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sha256_pdf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadatos: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "expediente_id"],
            ["expedientes_obra.tenant_id", "expedientes_obra.id"],
            name="fk_dibujo_bim_tenant_expediente",
        ),
    )
