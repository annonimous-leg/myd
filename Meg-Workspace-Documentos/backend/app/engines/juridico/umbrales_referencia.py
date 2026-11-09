# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

# DEPRECATED FOR RUNTIME (2026-09-09)
# ------------------------------------------------------------
# Los umbrales de procedimiento YA NO se leen desde este módulo.
# Runtime path: procedure_thresholds (DB) via ThresholdResolver.
# Este archivo se conserva únicamente como referencia histórica /
# fuente de datos para un seeder ETL hacia procedure_thresholds.
# NO importar desde motores de producción.
# ------------------------------------------------------------

"""
Umbrales de contratación pública por jurisdicción -- datos de referencia,
separados de la lógica del motor a propósito.

Por qué existe este archivo aparte: los montos máximos de adjudicación
directa/invitación restringida no son una constante fija en la ley -- se
publican cada ejercicio fiscal (federal: Anexo 9 del Presupuesto de
Egresos de la Federación, remitido desde el Art. 3 fracción X del
decreto de PEF; estados: su propio decreto/gaceta anual). Y a nivel
federal el Anexo 9 es una tabla ESCALONADA: el umbral que aplica depende
del presupuesto autorizado de la dependencia que contrata para esa
categoría de gasto (adquisiciones u obra pública) en el ejercicio, no
es un monto único para todo el gobierno.

Tres niveles de confianza por registro (campo `estado_dato`):
  - VERIFICADO: confirmado contra el texto primario oficial (DOF/gob.mx)
    leído directamente. El motor da respuesta definitiva.
  - CANDIDATO: citado por una fuente de investigación (propia o de
    terceros) con URL y contexto, pero SIN confirmar contra el
    documento primario -- el PDF oficial del Anexo 9 es tabla/imagen
    escaneada y no se pudo extraer texto de él pese a intentarlo
    repetidamente. El motor SÍ da una respuesta, pero la marca
    `datos_verificados=False` y `es_candidato=True` en todo momento --
    no se debe usar como fundamento único de una decisión de
    cumplimiento sin confirmar contra el documento primario.
  - PENDIENTE: no hay ningún dato, ni siquiera candidato. El motor se
    niega a responder (SIN_DETERMINAR).

Dos "candidatos" independientes (uno con asistencia de IA declarada,
otro sin declarar) coincidieron EXACTO en la tabla de Obra Pública
(mismas 15 cifras) pero difirieron 7x en la de Adquisiciones -- eso no
es tranquilizador, es sospechoso (ambos pudieron copiar del mismo
tercero no primario). Se cargó la versión más reciente/detallada como
candidato de todos modos porque es mejor que nada para pruebas, pero el
desacuerdo entre fuentes está documentado aquí explícitamente y el
campo `estado_dato` refleja que NINGUNA de las dos alcanza el nivel
VERIFICADO.

Para completar: cuando se tenga el Anexo 9 real confirmado (aunque sea
por una captura de pantalla leída con visión en vez de extracción de
texto), actualizar `estado_dato` a VERIFICADO en el registro
correspondiente. No hace falta tocar motor_juridico.py para esto.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional


class Jurisdiccion(str, Enum):
    """Extensible -- agregar aquí cuando se investigue un nuevo estado."""
    FEDERAL = "FEDERAL"
    CDMX = "CDMX"
    ESTADO_DE_MEXICO = "ESTADO_DE_MEXICO"
    JALISCO = "JALISCO"
    TLAXCALA = "TLAXCALA"


class TipoContratacionRef(str, Enum):
    """Separado de TipoContratacion (motor_juridico.py) a propósito --
    esa es la clasificación operativa del resto del sistema; esta es la
    clasificación tal como la usan las leyes de umbral (que en la
    práctica solo distinguen obra vs. todo lo demás)."""
    OBRA_PUBLICA = "OBRA_PUBLICA"
    ADQUISICIONES_SERVICIOS = "ADQUISICIONES_SERVICIOS"


class EstadoDato(str, Enum):
    VERIFICADO = "VERIFICADO"     # confirmado contra fuente primaria oficial
    CANDIDATO = "CANDIDATO"       # citado por investigación, sin confirmar
    PENDIENTE = "PENDIENTE"       # sin ningún dato


@dataclass
class TramoPresupuestal:
    """Un renglón de la tabla escalonada del Anexo 9. El umbral que
    aplica a una dependencia depende de SU presupuesto autorizado para
    esa categoría de gasto en el ejercicio -- no es un monto único."""
    presupuesto_min_miles: float
    presupuesto_max_miles: Optional[float]  # None = sin techo ("más de X")
    adjudicacion_directa_miles: float
    invitacion_restringida_miles: float
    # Solo aplica a obra pública (columna separada para "servicio
    # relacionado con obra pública", que tiene su propio umbral, más
    # bajo que el de obra pública en sí).
    adjudicacion_directa_servicio_miles: Optional[float] = None
    invitacion_restringida_servicio_miles: Optional[float] = None

    def en_rango(self, presupuesto_miles: float) -> bool:
        if presupuesto_miles < self.presupuesto_min_miles:
            return False
        if self.presupuesto_max_miles is not None and presupuesto_miles >= self.presupuesto_max_miles:
            return False
        return True


@dataclass
class UmbralProcedimiento:
    jurisdiccion: Jurisdiccion
    ley: str
    articulo_referencia: str
    tipo_contratacion: TipoContratacionRef
    ejercicio_fiscal: int
    tramos: List[TramoPresupuestal]
    fuente: str
    fecha_publicacion: Optional[date]
    estado_dato: EstadoDato
    notas: Optional[str] = None

    @property
    def verificado(self) -> bool:
        return self.estado_dato == EstadoDato.VERIFICADO

    @property
    def tiene_datos(self) -> bool:
        return self.estado_dato in (EstadoDato.VERIFICADO, EstadoDato.CANDIDATO) and bool(self.tramos)


# ─── Registro de umbrales ──────────────────────────────────────────────

UMBRALES: List[UmbralProcedimiento] = [
    # ─── FEDERAL: LOPSRM (obra pública) ───────────────────────────────
    # CANDIDATO: misma tabla citada por dos investigaciones independientes
    # (coincidencia exacta en las 15 filas), pero ninguna de las dos se
    # pudo confirmar contra el PDF primario del Anexo 9 (tabla/imagen
    # escaneada, sin texto extraíble tras intentos directos de fetch).
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.FEDERAL,
        ley="LOPSRM",
        articulo_referencia="Art. 43 LOPSRM, remitido por PEF 2026 Art. 3 fracc. X al Anexo 9",
        tipo_contratacion=TipoContratacionRef.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        tramos=[
            TramoPresupuestal(0, 15_000, 499, 3_776, 223, 2_868),
            TramoPresupuestal(15_000, 30_000, 590, 4_469, 294, 3_240),
            TramoPresupuestal(30_000, 50_000, 678, 5_079, 357, 3_981),
            TramoPresupuestal(50_000, 100_000, 753, 5_637, 403, 4_528),
            TramoPresupuestal(100_000, 150_000, 1_027, 7_642, 492, 5_649),
            TramoPresupuestal(150_000, 250_000, 1_189, 9_024, 537, 6_620),
            TramoPresupuestal(250_000, 350_000, 1_386, 10_522, 683, 7_621),
            TramoPresupuestal(350_000, 450_000, 1_588, 12_116, 781, 8_656),
            TramoPresupuestal(450_000, 600_000, 1_699, 12_968, 888, 10_148),
            TramoPresupuestal(600_000, 750_000, 1_993, 15_258, 1_066, 12_082),
            TramoPresupuestal(750_000, 1_000_000, 2_128, 16_276, 1_152, 12_981),
            TramoPresupuestal(1_000_000, 1_250_000, 2_591, 19_932, 1_340, 15_258),
            TramoPresupuestal(1_250_000, 1_500_000, 3_083, 23_617, 1_574, 17_819),
            TramoPresupuestal(1_500_000, 2_700_000, 3_471, 26_766, 1_760, 19_966),
            TramoPresupuestal(2_700_000, None, 3_893, 28_913, 1_975, 22_372),
        ],
        fuente="Citado por dos investigaciones independientes (coinciden exacto en las "
               "15 filas), ninguna confirmada contra el PDF primario del Anexo 9 "
               "(gob.mx/SHCP) -- ese PDF es tabla/imagen escaneada, no se pudo "
               "extraer texto tras fetch directo. Montos en MILES de pesos, sin IVA.",
        fecha_publicacion=date(2025, 11, 21),
        estado_dato=EstadoDato.CANDIDATO,
        notas="CONFIRMAR: leer directamente (captura/visión) la página del Anexo 9 "
              "para pasar de CANDIDATO a VERIFICADO.",
    ),

    # ─── FEDERAL: LAASSP (adquisiciones/servicios) ────────────────────
    # CANDIDATO con MENOS confianza que la de obra pública: dos fuentes
    # dieron cifras muy distintas entre sí para esta tabla (una plana en
    # ~$2.2M, otra escalonada de $309k a $1,145k) -- se carga la
    # escalonada por ser más detallada y consistente con la estructura
    # real del Anexo 9 (que si es escalonado para obra, debería serlo
    # también para adquisiciones), pero el desacuerdo entre fuentes es
    # una razón adicional para no subir esto a VERIFICADO sin confirmar.
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.FEDERAL,
        ley="LAASSP",
        articulo_referencia="Art. 42 LAASSP, remitido por PEF 2026 Art. 3 fracc. X al Anexo 9",
        tipo_contratacion=TipoContratacionRef.ADQUISICIONES_SERVICIOS,
        ejercicio_fiscal=2026,
        tramos=[
            TramoPresupuestal(0, 15_000, 309, 2_272),
            TramoPresupuestal(15_000, 30_000, 343, 2_649),
            TramoPresupuestal(30_000, 50_000, 376, 2_983),
            TramoPresupuestal(50_000, 100_000, 391, 3_264),
            TramoPresupuestal(100_000, 150_000, 492, 4_351),
            TramoPresupuestal(150_000, 250_000, 554, 5_165),
            TramoPresupuestal(250_000, 350_000, 624, 6_138),
            TramoPresupuestal(350_000, 450_000, 686, 7_068),
            TramoPresupuestal(450_000, 600_000, 697, 7_551),
            TramoPresupuestal(600_000, 750_000, 777, 8_880),
            TramoPresupuestal(750_000, 1_000_000, 790, 9_461),
            TramoPresupuestal(1_000_000, 1_250_000, 902, 11_547),
            TramoPresupuestal(1_250_000, 1_500_000, 1_023, 13_741),
            TramoPresupuestal(1_500_000, None, 1_145, 16_086),
        ],
        fuente="Citado por una investigación (no coincide con una segunda fuente "
               "anterior, que daba una cifra plana ~$2.2M en vez de escalonada -- "
               "desacuerdo documentado, no resuelto). Montos en MILES de pesos, sin IVA.",
        fecha_publicacion=date(2025, 11, 21),
        estado_dato=EstadoDato.CANDIDATO,
        notas="CONFIRMAR contra Anexo 9 real -- dos fuentes distintas dieron cifras "
              "incompatibles entre sí para esta tabla específica, más motivo para "
              "no confiar sin verificar.",
    ),

    # ─── CDMX ──────────────────────────────────────────────────────────
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.CDMX,
        ley="Por confirmar (verificar si sigue vigente como Ley de Obra Pública "
            "del Distrito Federal tras el cambio a Ciudad de México)",
        articulo_referencia="PENDIENTE",
        tipo_contratacion=TipoContratacionRef.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        tramos=[],
        fuente="No investigado en esta sesión.",
        fecha_publicacion=None,
        estado_dato=EstadoDato.PENDIENTE,
        notas="PENDIENTE: nombre de ley vigente y decreto de montos 2026 de CDMX.",
    ),

    # ─── ESTADO DE MÉXICO ──────────────────────────────────────────────
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.ESTADO_DE_MEXICO,
        ley="Ley de Contratación Pública del Estado de México y Municipios",
        articulo_referencia="PENDIENTE (nombre de ley confirmado vía edomex.gob.mx "
                             "en esta sesión; artículo y montos específicos no)",
        tipo_contratacion=TipoContratacionRef.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        tramos=[],
        fuente="Nombre de ley confirmado vía edomex.gob.mx. Montos del decreto 2026 no verificados.",
        fecha_publicacion=None,
        estado_dato=EstadoDato.PENDIENTE,
        notas="PENDIENTE: decreto de montos 2026 del Estado de México.",
    ),

    # ─── JALISCO ───────────────────────────────────────────────────────
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.JALISCO,
        ley="Por confirmar (referencia de memoria sin verificar en esta sesión)",
        articulo_referencia="PENDIENTE",
        tipo_contratacion=TipoContratacionRef.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        tramos=[],
        fuente="No investigado en esta sesión.",
        fecha_publicacion=None,
        estado_dato=EstadoDato.PENDIENTE,
        notas="PENDIENTE: nombre de ley vigente y decreto de montos.",
    ),

    # ─── TLAXCALA ──────────────────────────────────────────────────────
    # Ley y artículos VERIFICADOS -- leídos directo del texto primario
    # (PDF con capa de texto real generado por Word, no escaneado; última
    # reforma publicada en el Periódico Oficial del Estado el 24-may-2023).
    # Mismo patrón que federal: la ley remite los montos al Presupuesto
    # de Egresos del Estado (documento anual separado, no incluido en
    # este PDF) -- así que estado_dato sigue en PENDIENTE para los
    # montos en sí, aunque la ley/artículo ya estén confirmados.
    UmbralProcedimiento(
        jurisdiccion=Jurisdiccion.TLAXCALA,
        ley="Ley de Obras Públicas para el Estado de Tlaxcala y sus Municipios "
            "(última reforma: Periódico Oficial 24-may-2023)",
        articulo_referencia="Art. 48 (remite montos al Presupuesto de Egresos del Estado); "
                             "Art. 46-47 (excepciones a licitación pública); Art. 50 (tope "
                             "agregado 20% del presupuesto de obra pública, igual que LOPSRM federal)",
        tipo_contratacion=TipoContratacionRef.OBRA_PUBLICA,
        ejercicio_fiscal=2026,
        tramos=[],
        fuente="Ley de Obras Públicas Tlaxcala y sus Municipios-240523.pdf -- PDF con texto "
               "real (no escaneado), leído directo con pdftotext, artículos confirmados. "
               "Los montos máximos NO están en la ley -- el Art. 48 remite al Presupuesto "
               "de Egresos del Estado de Tlaxcala del ejercicio correspondiente, que no se ha "
               "conseguido todavía.",
        fecha_publicacion=date(2023, 5, 24),
        estado_dato=EstadoDato.PENDIENTE,
        notas="Ley y artículos VERIFICADOS contra texto primario. Solo falta el "
              "Presupuesto de Egresos del Estado de Tlaxcala 2026 (o el ejercicio "
              "vigente) para los montos en miles de pesos.",
    ),
]


def buscar_umbral(
    jurisdiccion: Jurisdiccion,
    tipo_contratacion: TipoContratacionRef,
    ejercicio_fiscal: int,
) -> Optional[UmbralProcedimiento]:
    for u in UMBRALES:
        if (u.jurisdiccion == jurisdiccion and u.tipo_contratacion == tipo_contratacion
                and u.ejercicio_fiscal == ejercicio_fiscal):
            return u
    return None


def buscar_tramo(
    umbral: UmbralProcedimiento, presupuesto_dependencia_miles: Optional[float],
) -> Optional[TramoPresupuestal]:
    """Encuentra el tramo aplicable según el presupuesto autorizado de la
    dependencia. Si no se da presupuesto_dependencia_miles, no se puede
    elegir tramo -- regresa None (el motor debe manejar esto como "falta
    un dato" en vez de adivinar cuál tramo aplica)."""
    if not umbral.tramos or presupuesto_dependencia_miles is None:
        return None
    for t in umbral.tramos:
        if t.en_rango(presupuesto_dependencia_miles):
            return t
    return umbral.tramos[-1] if presupuesto_dependencia_miles > 0 else None


def jurisdicciones_disponibles() -> List[Dict[str, object]]:
    """Para poblar un selector en el frontend."""
    resumen: Dict[Jurisdiccion, EstadoDato] = {}
    orden = {EstadoDato.PENDIENTE: 0, EstadoDato.CANDIDATO: 1, EstadoDato.VERIFICADO: 2}
    for u in UMBRALES:
        # BUG ORIGINAL: comparar contra resumen.get(..., PENDIENTE) con
        # ">" (estricto) hacía que una jurisdicción cuyo ÚNICO registro
        # fuera PENDIENTE nunca se insertara en `resumen` (0 > 0 es
        # False), así que jurisdicciones sin ningún dato candidato
        # desaparecían por completo de la lista en vez de aparecer como
        # PENDIENTE. Se corrige insertando explícitamente en la primera
        # aparición de cada jurisdicción.
        if u.jurisdiccion not in resumen or orden[u.estado_dato] > orden[resumen[u.jurisdiccion]]:
            resumen[u.jurisdiccion] = u.estado_dato
    return [{"jurisdiccion": j.value, "estado_dato": e.value} for j, e in resumen.items()]
