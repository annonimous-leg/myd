# Copyright © 2026 Cristian Rodriguez
# All rights reserved.

"""
Módulo LEGL v3.0 — Consultor Legal Sin IA
- Motor de búsqueda con 969 artículos indexados
- 50+ sinónimos para búsqueda semántica
- 10 categorías temáticas
- 15 intenciones detectadas
- Conectado al motor jurídico existente

CORREGIDO: el archivo completo no compilaba. La causa raíz eran decenas
de f-strings/strings multilínea escritos con comillas simples (f"...")
que contenían saltos de línea literales sin cerrar -- en Python eso solo
es válido con comillas triples (f\"\"\"...\"\"\"). Se normalizó cada bloque de
`respuesta` a comillas triples. Además, chat_legal() tenía dos bugs de
lógica real (no solo de sintaxis):
  1. Llamaba a determinar_procedimiento(...) como función normal y luego
     hacía `resultado = res.body` -- determinar_procedimiento devuelve un
     dict plano (es un handler de FastAPI, no un objeto Response), así
     que .body no existe: esto tronaba con AttributeError la primera vez
     que alguien preguntaba "¿qué procedimiento para X millones?" (el
     propio saludo del bot sugiere esa pregunta como ejemplo). El valor
     tampoco se usaba después (todo se recalculaba línea seguido), así
     que se quitó la llamada muerta.
  2. `for cat_id, cat_data in _motor.listar_categorias():` asumía que el
     motor regresaba pares (id, data), pero listar_categorias() regresa
     una lista de dicts (cada uno ya trae su propio "id"). Se corrigió el
     desempaquetado.
CORREGIDO 2026-09-01 (hallazgo F-01 de auditoría externa): este archivo
tenía SU PROPIA lógica de umbrales -- UMBRAL_AD_PLACEHOLDER=1_000_000 /
UMBRAL_IR_PLACEHOLDER=50_000_000, un solo nivel fijo -- que existía en
paralelo al motor jurídico real (app/engines/juridico/motor_juridico.py +
umbrales_referencia.py), que YA implementa la tabla escalonada verdadera
por presupuesto autorizado de dependencia, con manejo fail-closed
(SIN_DETERMINAR cuando falta un dato) y trazabilidad VERIFICADO/
CANDIDATO/PENDIENTE por registro. Ese motor ya está expuesto en
/juridico/procedimiento (backend/app/api/v1/juridico.py) y ya lo consume
el frontend en megalodon-costos/index.tsx. Este endpoint /legal/procedimiento
y el chatbot de este archivo simplemente nunca lo llamaban -- calculaban su
propia respuesta con el placeholder de un solo nivel, dándole al usuario
la ilusión de una determinación legal real. Eliminados
UMBRAL_AD_PLACEHOLDER/UMBRAL_IR_PLACEHOLDER/_determinar_procedimiento_umbral().
Ahora todo el archivo (endpoint REST y las 3 intenciones del chatbot que
tocan monto: procedimiento/plazos/checklist) delega en JuridicoService,
la misma puerta de entrada que ya usa /juridico/procedimiento. No se
duplica lógica de umbral en ningún lado de este archivo.
"""
from app.core.rate_limit import rate_limit_standard, rate_limit_strict
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Optional
from datetime import date
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User, Tenant
from app.core.errors import handle_megalodon_errors, MegalodonException, ErrorCode
from app.services.entitlements_service import EntitlementsService
from app.services.juridico_service import JuridicoService
from app.core.calendar import CalendarioLaboral

# Importar motor de búsqueda
from app.engines.juridico.motor_busqueda_legal import MotorBusquedaLegal
from app.engines.juridico.motor_garantias import MotorGarantiasPenalizaciones

router = APIRouter(tags=["Consultor Legal LEGL"])  # prefijo va solo en router.py

# Instancia singleton
_motor = MotorBusquedaLegal()
_motor_garantias = MotorGarantiasPenalizaciones()

# Nombres legibles del enum TipoProcedimiento del motor (ADJUDICACION_DIRECTA/
# INVITACION_TRES/LICITACION_PUBLICA/SIN_DETERMINAR) hacia el vocabulario que
# ya usan este endpoint y el frontend de LEGL (adjudicacion_directa/
# invitacion_restringida/licitacion_publica).
_PROC_A_CLAVE = {
    "ADJUDICACION_DIRECTA": "adjudicacion_directa",
    "INVITACION_TRES": "invitacion_restringida",
    "LICITACION_PUBLICA": "licitacion_publica",
}
_PROC_A_NOMBRE = {
    "adjudicacion_directa": "Adjudicación Directa",
    "invitacion_restringida": "Invitación Restringida (a cuando menos tres personas)",
    "licitacion_publica": "Licitación Pública",
}

# Plazos mínimos por procedimiento (días hábiles de publicación + recepción
# de proposiciones). Esto es un dato legal DISTINTO al umbral de monto: no
# depende del presupuesto de la dependencia, depende del tipo de
# procedimiento (LOPSRM Art. 33 / LAASSP Art. 32 fijan plazos mínimos según
# procedimiento y si es nacional/internacional). El foco de esta corrección
# fue F-01 (el umbral de monto); estos días NO fueron reverificados letra
# por letra contra el texto en esta sesión -- se conservan los mismos
# valores que ya traía el código, pero consolidados en UN solo lugar en vez
# de las 4 copias independientes que había (endpoint, chat "procedimiento",
# chat "plazos", chat "checklist"). Pendiente: confirmar contra LOPSRM
# Art. 33 / LAASSP Art. 32 con el mismo rigor que ya se aplicó al umbral.
_PLAZOS_POR_PROCEDIMIENTO = {
    "adjudicacion_directa": {"publicacion_dias_habiles": 0, "recepcion_dias_habiles": 3},
    "invitacion_restringida": {"publicacion_dias_habiles": 5, "recepcion_dias_habiles": 10},
    "licitacion_publica": {"publicacion_dias_habiles": 10, "recepcion_dias_habiles": 20},
}


def _plazos_para(procedimiento_clave: str) -> dict:
    p = _PLAZOS_POR_PROCEDIMIENTO.get(procedimiento_clave, {"publicacion_dias_habiles": 0, "recepcion_dias_habiles": 0})
    return {**p, "total_minimo": p["publicacion_dias_habiles"] + p["recepcion_dias_habiles"]}


_JURISDICCION_A_PROFILE = {
    "FEDERAL": "MX-FED-OBRA",
    "MX-FED-OBRA": "MX-FED-OBRA",
    "MX-FED-ADQ": "MX-FED-ADQ",
    "CDMX": "MX-CDMX-OBRA",
    "ESTADO_DE_MEXICO": "MX-EM-OBRA",
    "JALISCO": "MX-JAL-OBRA",
    "TLAXCALA": "MX-TLAX-OBRA",
}


async def _consultar_motor_juridico(
    db: AsyncSession,
    monto: float,
    tipo_obra: str = "obra_publica",
    presupuesto_dependencia_miles: Optional[float] = None,
    jurisdiccion: str = "FEDERAL",
    ejercicio_fiscal: int = 2026,
    excepcion_legal: Optional[str] = None,
    justificacion_excepcion: Optional[str] = None,
    investigacion_mercado_realizada: bool = False,
    tenant_id=None,
) -> dict:
    """Única puerta de entrada de este archivo al motor jurídico real (DB)."""
    tipo_contratacion = "OBRA_PUBLICA" if tipo_obra == "obra_publica" else "ADQUISICION"
    code = _JURISDICCION_A_PROFILE.get(str(jurisdiccion).upper(), str(jurisdiccion).upper())
    if tipo_obra != "obra_publica" and code == "MX-FED-OBRA":
        code = "MX-FED-ADQ"
    return await JuridicoService(db, tenant_id=tenant_id).determinar_procedimiento(
        monto=monto,
        tipo_contratacion=tipo_contratacion,
        es_obra_publica=(tipo_obra == "obra_publica"),
        jurisdiction_code=code,
        ejercicio_fiscal=ejercicio_fiscal,
        presupuesto_dependencia_miles=presupuesto_dependencia_miles,
        excepcion_legal=excepcion_legal,
        justificacion_excepcion=justificacion_excepcion,
        investigacion_mercado_realizada=investigacion_mercado_realizada,
        tenant_id=tenant_id,
    )


async def _registrar_consulta_legl(db: AsyncSession, current_user: User) -> None:
    """Cuenta esta llamada contra max_consultas_legl_mes del tenant.

    BUG ORIGINAL: el límite de consultas LEGL vivía en PlanLimite y
    EntitlementsService.verificar_y_registrar_uso() ya sabía aplicarlo,
    pero ningún endpoint de LEGL lo llamaba -- un tenant Free tenía
    consultas LEGL ilimitadas en la práctica, pese a que el plan dice 10/mes.
    """
    tenant = await db.get(Tenant, current_user.tenant_id)
    await EntitlementsService(db).verificar_y_registrar_uso(tenant, "consultas_legl")

# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS BASE
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/consultar")
@handle_megalodon_errors
async def consultar_legal(
    query: str,
    ley: Optional[str] = None,
    fase: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Consulta el corpus legal por palabras clave con búsqueda semántica."""
    await _registrar_consulta_legl(db, current_user)
    resultados = _motor.buscar(query, ley, fase, max_resultados=10)
    return {
        "query": query,
        "filtros": {"ley": ley, "fase": fase},
        "total": len(resultados),
        "resultados": resultados,
    }

@router.post("/procedimiento")
@handle_megalodon_errors
async def determinar_procedimiento(
    monto: float,
    tipo_obra: str = "obra_publica",
    presupuesto_dependencia_miles: Optional[float] = None,
    jurisdiccion: str = "FEDERAL",
    ejercicio_fiscal: int = 2026,
    excepcion_legal: Optional[str] = None,
    justificacion_excepcion: Optional[str] = None,
    investigacion_mercado_realizada: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Determina el procedimiento de contratación según el Anexo 9 del PEF.

    CORREGIDO (F-01): ya no calcula con un umbral de un solo nivel
    inventado en este archivo -- delega en JuridicoService/MotorJuridico,
    el motor real con tabla escalonada por presupuesto de dependencia y
    comportamiento fail-closed. `presupuesto_dependencia_miles` (en MILES
    de pesos) es indispensable para jurisdicción FEDERAL: el Anexo 9 no es
    un monto único, es una tabla por presupuesto autorizado de la
    dependencia para esa categoría de gasto en el ejercicio. Sin ese dato,
    o sin tabla cargada para la jurisdicción/año pedidos, la respuesta
    viene con "determinado": false y la razón en "observaciones" -- eso no
    es un error del sistema, es el motor negándose a adivinar.
    """
    resultado = await _consultar_motor_juridico(
        db, monto, tipo_obra, presupuesto_dependencia_miles, jurisdiccion, ejercicio_fiscal,
        excepcion_legal=excepcion_legal,
        justificacion_excepcion=justificacion_excepcion,
        investigacion_mercado_realizada=investigacion_mercado_realizada,
        tenant_id=current_user.tenant_id,
    )

    if not resultado["valido"]:
        return {
            "determinado": False,
            "procedimiento": None,
            "nombre": "No determinado",
            "monto": monto,
            "tipo_obra": tipo_obra,
            "observaciones": resultado["observaciones"],
            "datos_verificados": False,
            "es_candidato": resultado["es_candidato"],
        }

    procedimiento = _PROC_A_CLAVE.get(resultado["procedimiento"], resultado["procedimiento"])
    nombre = _PROC_A_NOMBRE.get(procedimiento, procedimiento)
    just = resultado.get("justificacion") or {}
    meta = resultado.get("threshold_meta") or {}
    if just.get("ley") or just.get("articulo"):
        base_legal = f"{just.get('ley', '')} {just.get('articulo', '')}".strip()
    elif meta.get("ley") or meta.get("articulo_referencia"):
        base_legal = f"{meta.get('ley', '')} {meta.get('articulo_referencia', '')}".strip()
    else:
        base_legal = resultado.get("fuente_umbral")
    requisitos_motor = []
    if just.get("requisitos"):
        requisitos_motor = [{"descripcion": r, "obligatorio": True} for r in just["requisitos"]]

    # Buscar requisitos en el corpus REAL (además de los que ya regresa el
    # motor jurídico en resultado["requisitos"])
    requisitos_corpus = _motor.buscar(f"{procedimiento} requisitos", max_resultados=5)

    # Garantías solo desde LegalRule en DB (fail-closed si no hay regla).
    # Seriedad: sin regla sembrada → PENDIENTE_REGLA (no inventar 5%).
    jcode = jurisdiccion if jurisdiccion and jurisdiccion != "FEDERAL" else "MX-FED-OBRA"
    monto_min, gdec = await _motor_garantias.calcular_garantia_cumplimiento(
        db,
        monto,
        tenant_id=current_user.tenant_id,
        jurisdiction_code=jcode,
        tipo_contrato=tipo_obra,
    )
    garantias_requeridas = {
        "seriedad": {
            "estado": "PENDIENTE_REGLA",
            "porcentaje": None,
            "monto_minimo": None,
            "nota": "Sin LegalRule de seriedad de propuestas en seeds; no se inventa porcentaje.",
        },
        "cumplimiento": {
            "estado": "OK" if gdec.found else "SIN_REGLA",
            "porcentaje": (gdec.percentage * 100) if gdec.found and gdec.percentage is not None else None,
            "monto_minimo": monto_min if gdec.found else None,
            "rule_id": gdec.rule_id,
            "ley": gdec.ley,
            "articulo": gdec.articulo,
            "error": gdec.error,
        },
    }

    return {
        "determinado": True,
        "procedimiento": procedimiento,
        "nombre": nombre,
        "monto": monto,
        "tipo_obra": tipo_obra,
        "base_legal": base_legal,
        "requisitos": requisitos_corpus,
        "requisitos_juridicos": requisitos_motor or resultado.get("requisitos", []),
        "plazos": _plazos_para(procedimiento),
        "publicacion_obligatoria": procedimiento != "adjudicacion_directa",
        "garantias_requeridas": garantias_requeridas,
        "umbrales": resultado["umbrales"],
        "datos_verificados": resultado["datos_verificados"],
        "es_candidato": resultado["es_candidato"],
        "fuente_umbral": resultado["fuente_umbral"],
        "observaciones": resultado["observaciones"],
    }


def _sumar_dias_habiles_cruzando_anio(inicio: date, dias: int) -> date:
    """CalendarioLaboral genera sus festivos para un solo año fijo en
    __init__ -- si el rango de días hábiles cruza el 31 de diciembre, los
    festivos del año siguiente no estarían cargados y esos días se
    tratarían como hábiles por defecto. Plazos de LOPSRM/LAASSP rara vez
    cruzan el año (10-20 días hábiles), pero es un caso real posible
    (ej. arrancar un plazo el 20 de diciembre); se reinstancia el
    calendario para el año de llegada si el resultado cae en otro año."""
    cal = CalendarioLaboral(year=inicio.year)
    resultado = cal.sumar_dias_habiles(inicio, dias)
    if resultado.year != inicio.year:
        cal = CalendarioLaboral(year=resultado.year)
        resultado = cal.sumar_dias_habiles(inicio, dias)
    return resultado


@router.post("/calcular-fechas")
@handle_megalodon_errors
async def calcular_fechas_procedimiento(
    fecha_inicio: str,
    procedimiento: str,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Calcula fecha de cierre y fecha de fallo estimadas a partir de una
    fecha de inicio, en DÍAS HÁBILES reales (LFT Art. 74 vía
    app/core/calendar.py -- el mismo calendario que ya usa el módulo de
    programación/CPM).

    CORREGIDO (contra-auditoría V8 sobre F-01): CalculadoraPlazos.tsx
    calculaba estas fechas en el navegador con
    `Date.setDate(Date.getDate() + N)` -- días CALENDARIO, ignorando
    sábados/domingos/festivos, pese a que tanto la UI como la ley hablan
    de días HÁBILES. El backend ya tenía un calendario laboral real y
    probado (usado por CPM) que nadie exponía para este cálculo.
    """
    proc = procedimiento if procedimiento in _PLAZOS_POR_PROCEDIMIENTO else None
    if proc is None:
        raise MegalodonException(
            ErrorCode.NORMATIVO_GENERICO,
            f"procedimiento inválido: '{procedimiento}'. Use uno de: {list(_PLAZOS_POR_PROCEDIMIENTO)}.",
            status_code=400,
        )
    try:
        inicio = date.fromisoformat(fecha_inicio)
    except ValueError:
        raise MegalodonException(
            ErrorCode.NORMATIVO_GENERICO, "fecha_inicio inválida, use formato YYYY-MM-DD.", status_code=400,
        )

    plazos = _plazos_para(proc)
    cierre = _sumar_dias_habiles_cruzando_anio(inicio, plazos["total_minimo"])
    # 5 días hábiles adicionales para el fallo tras el cierre -- mismo
    # supuesto que ya traía CalculadoraPlazos.tsx, ahora en días hábiles
    # reales en vez de días calendario.
    fallo = _sumar_dias_habiles_cruzando_anio(cierre, 5)

    return {
        "fecha_inicio": inicio.isoformat(),
        "fecha_cierre_estimada": cierre.isoformat(),
        "fecha_fallo_estimada": fallo.isoformat(),
        "plazos": plazos,
    }


@router.get("/articulo/{ley}/{numero}")
@handle_megalodon_errors
async def obtener_articulo(
    ley: str,
    numero: str,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard),
):
    """Obtiene un artículo específico del corpus REAL de 969 artículos."""
    resultado = _motor.obtener_articulo(ley, numero)
    if not resultado:
        raise HTTPException(status_code=404, detail="Artículo no encontrado en el corpus")
    return resultado

@router.get("/leyes")
@handle_megalodon_errors
async def listar_leyes(current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)):
    """Lista todas las leyes disponibles."""
    return {"leyes": _motor.listar_leyes()}

@router.get("/categorias")
@handle_megalodon_errors
async def listar_categorias(current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_standard)):
    """Lista las categorías temáticas disponibles."""
    return {"categorias": _motor.listar_categorias()}


@router.get('/cobertura')
@handle_megalodon_errors
async def cobertura_corpus(current_user: User = Depends(get_current_user),
                           _rate_limit: bool = Depends(rate_limit_standard)):
    return _motor.cobertura()

@router.post("/categoria/{categoria_id}")
@handle_megalodon_errors
async def buscar_por_categoria(
    categoria_id: str,
    max_resultados: int = 10,
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Busca artículos por categoría temática."""
    resultados = _motor.buscar_por_categoria(categoria_id, max_resultados)
    return {
        "categoria": categoria_id,
        "total": len(resultados),
        "resultados": resultados,
    }

# ═══════════════════════════════════════════════════════════════════════════
# CHATBOT v3.0 — 15 INTENCIONES + CORPUS REAL
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/chat")
@handle_megalodon_errors
async def chat_legal(
    mensaje: str,
    contexto: Optional[List[Dict]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user), _rate_limit: bool = Depends(rate_limit_strict),
):
    """Chatbot legal sin IA — 15 intenciones + búsqueda en corpus real de 969 artículos."""
    await _registrar_consulta_legl(db, current_user)

    mensaje_lower = mensaje.lower()
    intencion = "consulta_general"
    parametros = {}

    # ═══════════════════════════════════════════════════════════════════
    # DETECCIÓN DE INTENCIONES (15 intenciones)
    # ═══════════════════════════════════════════════════════════════════

    # 1. SALUDO / AYUDA
    if any(p in mensaje_lower for p in ["hola", "buenos dias", "buenas tardes", "ayuda", "que puedes hacer", "qué puedes hacer", "funciones", "capacidades", "quien eres", "quién eres"]):
        intencion = "saludo"

    # 2. PROCEDIMIENTO
    elif any(p in mensaje_lower for p in ["procedimiento", "monto", "millones", "pesos", "$", "cuanto", "cuánto", "adjudicacion", "licitacion", "invitacion", "directa", "publica", "restringida"]):
        intencion = "procedimiento"
        numeros = re.findall(r"[\d,]+(?:\.\d+)?", mensaje)
        if numeros:
            parametros["monto"] = max([float(n.replace(",", "")) for n in numeros])

    # 3. ARTÍCULO ESPECÍFICO
    elif any(p in mensaje_lower for p in ["artículo", "articulo", "art.", "art ", "numero", "número"]):
        intencion = "articulo"
        match = re.search(r"art[íi]culo\s+(\d+[A-Z]?)", mensaje_lower)
        if match:
            parametros["numero"] = match.group(1)
        else:
            match2 = re.search(r"(?:art|n[úu]mero|num)\s*[:\s]*(\d+)", mensaje_lower)
            if match2:
                parametros["numero"] = match2.group(1)
        if "lopsrm" in mensaje_lower or "obras" in mensaje_lower:
            parametros["ley"] = "lopsrm"
        elif "laassp" in mensaje_lower or "adquisiciones" in mensaje_lower:
            parametros["ley"] = "laassp"
        elif "lgra" in mensaje_lower or "responsabilidades" in mensaje_lower:
            parametros["ley"] = "lgra"
        elif "reglamento" in mensaje_lower:
            if "laassp" in mensaje_lower:
                parametros["ley"] = "reglamento_laassp"
            elif "lopsrm" in mensaje_lower:
                parametros["ley"] = "reglamento_lopsrm"

    # 4. COMPARAR ARTÍCULOS
    elif any(p in mensaje_lower for p in ["compara", "comparar", "diferencia", "versus", "vs", "ambas leyes", "diferencias entre", "en común"]):
        intencion = "comparar"
        match = re.search(r"(?:art[íi]culo\s+|art\.?\s*|n[úu]mero\s*)?(\d+[A-Z]?)", mensaje_lower)
        if match:
            parametros["numero"] = match.group(1)

    # 5. PLAZOS / FECHAS
    elif any(p in mensaje_lower for p in ["plazo", "fecha", "dias", "días", "calendario", "cuando", "cuándo", "tiempo", "cuanto tiempo", "prorroga", "extensión"]):
        intencion = "plazos"
        numeros = re.findall(r"[\d,]+(?:\.\d+)?", mensaje)
        if numeros:
            parametros["monto"] = float(numeros[0].replace(",", ""))

    # 6. CHECKLIST / REQUISITOS
    elif any(p in mensaje_lower for p in ["checklist", "requisitos", "pasos", "que necesito", "qué necesito", "documentos", "lista", "paso a paso", "que debo presentar"]):
        intencion = "checklist"
        numeros = re.findall(r"[\d,]+(?:\.\d+)?", mensaje)
        if numeros:
            parametros["monto"] = float(numeros[0].replace(",", ""))

    # 7. GARANTÍAS
    elif any(p in mensaje_lower for p in ["garantia", "fianza", "caucion", "caución", "aval", "seriedad", "cumplimiento", "vicios ocultos"]):
        intencion = "garantias"
        numeros = re.findall(r"[\d,]+(?:\.\d+)?", mensaje)
        if numeros:
            parametros["monto"] = float(numeros[0].replace(",", ""))

    # 8. FASE DEL PROCESO
    elif any(p in mensaje_lower for p in ["planeación", "planeacion", "convocatoria", "proposición", "proposicion", "evaluación", "evaluacion", "fallo", "contrato", "ejecución", "ejecucion", "finiquito", "entrega", "recepcion", "recepción"]):
        intencion = "fase"
        fases_map = {
            "planeación": "planeacion", "planeacion": "planeacion",
            "convocatoria": "convocatoria",
            "proposición": "proposiciones", "proposicion": "proposiciones",
            "evaluación": "evaluacion", "evaluacion": "evaluacion",
            "fallo": "fallo",
            "contrato": "contrato",
            "ejecución": "ejecucion", "ejecucion": "ejecucion",
            "finiquito": "finiquito",
            "entrega": "finiquito", "recepcion": "finiquito", "recepción": "finiquito",
        }
        for k, v in fases_map.items():
            if k in mensaje_lower:
                parametros["fase"] = v
                break

    # 9. AJUSTE DE COSTOS / INPC / UMA
    elif any(p in mensaje_lower for p in ["inpc", "uma", "ajuste", "costos", "precio", "incremento", "inflacion", "inflación", "variación", "variacion"]):
        intencion = "ajuste_costos"

    # 10. SANCIONES / RESPONSABILIDADES / SFP
    elif any(p in mensaje_lower for p in ["sancion", "sanción", "multa", "castigo", "pena", "sfp", "secretaria funcion publica", "responsabilidad administrativa", "infraccion", "falta grave"]):
        intencion = "sanciones"

    # 11. ABANDONO DE OBRA / INCUMPLIMIENTO
    elif any(p in mensaje_lower for p in ["abandono", "abandonar", "desistimiento", "retiro", "contratista no", "no cumple", "incumplimiento", "no ejecuta", "no trabaja"]):
        intencion = "abandono_obra"

    # 12. RECURSOS DE INCONFORMIDAD
    elif any(p in mensaje_lower for p in ["inconformidad", "protesta", "queja", "recurso de revision", "revision", "apelacion", "apelación", "impugnacion", "impugnación", "no estoy de acuerdo", "discordar"]):
        intencion = "recursos_inconformidad"

    # 13. SUBCONTRATACIÓN / TERCERIZACIÓN
    elif any(p in mensaje_lower for p in ["subcontratacion", "subcontratación", "subcontrato", "tercerizar", "tercerizacion", "tercerización", "delegar", "encargar", "subcontratista"]):
        intencion = "subcontratacion"

    # 14. TRANSPARENCIA / ACCESO A INFO
    elif any(p in mensaje_lower for p in ["transparencia", "informacion publica", "información pública", "acceso a la informacion", "publicar", "difundir", "compranet", "plataforma"]):
        intencion = "transparencia"

    # 15. SUPERVISIÓN / FISCALIZACIÓN
    elif any(p in mensaje_lower for p in ["supervision", "supervisión", "fiscalizacion", "fiscalización", "vigilar", "monitoreo", "inspector", "supervisor", "auditoria", "auditoría"]):
        intencion = "supervision"

    # ═══════════════════════════════════════════════════════════════════
    # GENERAR RESPUESTA CON CORPUS REAL
    # ═══════════════════════════════════════════════════════════════════

    if intencion == "saludo":
        respuesta = """👋 ¡Hola! Soy LEGL, tu asistente legal experto.

Puedo ayudarte con cualquier tema de contratación pública:

💬 **Chat** — Pregúntame lo que sea sobre LOPSRM, LAASSP, LGRA, reglamentos
⚖️ **Comparador** — Compara artículos entre leyes
📅 **Plazos** — Calcula fechas según el monto
✅ **Checklist** — Genera listas de requisitos

**Ejemplos de consultas:**
• "¿Qué procedimiento para 5 millones?"
• "Artículo 40 LOPSRM"
• "Compara el artículo 52"
• "¿Qué sanciones aplica la SFP?"
• "¿Qué pasa si el contratista abandona?"
• "Requisitos de licitación pública"
• "Recursos de inconformidad"
• "Subcontratación en obra pública"

¿Qué necesitas?"""

    elif intencion == "procedimiento" and "monto" in parametros:
        # CORREGIDO (F-01): ya no calcula con el placeholder de un solo
        # nivel (1M/50M). Consulta el motor jurídico real (misma puerta que
        # el endpoint REST) vía _consultar_motor_juridico(). El chat no
        # tiene forma confiable de extraer "presupuesto autorizado de la
        # dependencia" de una frase libre sin arriesgar una lectura
        # equivocada, así que se manda sin ese dato -- el motor responde
        # SIN_DETERMINAR y aquí se explica honestamente por qué, en vez de
        # aparentar una respuesta segura con un umbral inventado.
        monto = parametros["monto"]
        resultado = await _consultar_motor_juridico(db, monto)

        if not resultado["valido"]:
            respuesta = f"""📋 **Todavía no puedo determinar el procedimiento**

💰 **Monto:** ${monto:,.0f} MXN

⚠️ El umbral de LOPSRM Art. 43 / LAASSP Art. 55 no es un monto único: es una tabla escalonada del Anexo 9 del PEF según el **presupuesto autorizado de tu dependencia** para esta categoría de gasto en el ejercicio. Sin ese dato no puedo darte un procedimiento confiable -- adivinar sería peor que no responder.

💡 Usa la **calculadora de plazos** o el **generador de checklist** en el panel derecho: ahí puedes capturar también el presupuesto autorizado de la dependencia (en miles de pesos) para obtener el procedimiento exacto."""
        else:
            proc = _PROC_A_CLAVE.get(resultado["procedimiento"], resultado["procedimiento"])
            nom = _PROC_A_NOMBRE.get(proc, proc)
            plazos = _plazos_para(proc)
            requisitos = _motor.buscar(f"{proc} requisitos", max_resultados=5)

            respuesta = f"""📋 **{nom}**

💰 **Monto:** ${monto:,.0f} MXN
📖 **Base legal:** {resultado.get('fuente_umbral') or 'LOPSRM Art. 43 / LAASSP Art. 55 (Anexo 9 del PEF)'}
⏱️ **Plazo mínimo:** {plazos['total_minimo']} días hábiles
📢 **Publicación obligatoria:** {'Sí ✅' if proc != 'adjudicacion_directa' else 'No ❌'}

💵 **Garantías:**
• Seriedad: PENDIENTE_REGLA (sin LegalRule sembrada; no se inventa %)
• Cumplimiento: según LegalRule en DB (no hardcode; ver endpoint determinar-procedimiento)

📚 **Requisitos del corpus:**
"""
            if requisitos:
                for req in requisitos[:3]:
                    respuesta += f"• {req['titulo'][:60]}...\n"
            else:
                respuesta += "(Sin coincidencias específicas en el corpus para este procedimiento.)\n"
            if resultado["es_candidato"]:
                respuesta += "\n⚠️ **Cifras sin confirmar:** el umbral usado viene de una tabla citada por investigación, todavía sin confirmar contra el Anexo 9 oficial. No la uses como único fundamento de una decisión de cumplimiento."
            respuesta += "\n\n💡 ¿Quieres que genere un checklist o calcule las fechas exactas?"

    elif intencion == "articulo" and "numero" in parametros:
        ley = parametros.get("ley", "lopsrm")
        art = _motor.obtener_articulo(ley, parametros["numero"])
        if art:
            respuesta = f"""📖 **{art['ley_nombre']}**

**Artículo {art['articulo']}**

{art['contenido'][:800]}

{'... (continúa)' if len(art['contenido']) > 800 else ''}

📊 **Longitud:** {art['longitud']} caracteres

💡 ¿Quieres comparar este artículo con la otra ley?"""
        else:
            # Buscar similares
            similares = _motor.buscar(f"artículo {parametros['numero']}", max_resultados=3)
            respuesta = f"""❌ No encontré el artículo {parametros['numero']} en {ley.upper()}.

🔍 Artículos similares:
"""
            if similares:
                for s in similares:
                    respuesta += f"• {s['ley_nombre']} Art. {s['articulo']}: {s['titulo'][:60]}...\n"
            else:
                respuesta += "No se encontraron artículos similares en el corpus.\n"

    elif intencion == "comparar" and "numero" in parametros:
        num = parametros["numero"]
        lopsrm = _motor.obtener_articulo("lopsrm", num)
        laassp = _motor.obtener_articulo("laassp", num)
        reg_lopsrm = _motor.obtener_articulo("reglamento_lopsrm", num)
        reg_laassp = _motor.obtener_articulo("reglamento_laassp", num)

        respuesta = f"""⚖️ **Comparación — Artículo {num}**

"""
        if lopsrm:
            respuesta += f"""🔵 **LOPSRM**
{lopsrm['titulo'][:80]}
{lopsrm['contenido'][:350]}...

"""
        if laassp:
            respuesta += f"""🟢 **LAASSP**
{laassp['titulo'][:80]}
{laassp['contenido'][:350]}...

"""
        if reg_lopsrm:
            respuesta += f"""🔷 **Reglamento LOPSRM**
{reg_lopsrm['contenido'][:300]}...

"""
        if reg_laassp:
            respuesta += f"""🟩 **Reglamento LAASSP**
{reg_laassp['contenido'][:300]}...

"""
        if not any([lopsrm, laassp, reg_lopsrm, reg_laassp]):
            respuesta = f"❌ No encontré el artículo {num} en ninguna ley."
        else:
            respuesta += "💡 **Análisis:** LOPSRM regula obras públicas y servicios relacionados. LAASSP abarca adquisiciones, arrendamientos y servicios del sector público en general. Los reglamentos desarrollan procedimientos específicos."

    elif intencion == "sanciones":
        resultados = _motor.buscar("sanciones responsabilidad SFP", max_resultados=8)
        respuesta = """⚖️ **Sanciones y Responsabilidades**

"""
        if resultados:
            respuesta += f"""Encontré {len(resultados)} artículos relacionados:

"""
            for r in resultados[:5]:
                respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:200]}...

"""
        else:
            respuesta += """🔍 Consultando el corpus sobre sanciones...

"""
        respuesta += """💡 **Tipos de sanciones (LGRA):**
• **Leves:** Amonestación pública, suspensión
• **Graves:** Destitución, inhabilitación
• **Muy graves:** Sanciones económicas, penalidades

📖 **Base legal principal:** LGRA, LOPSRM Art. 60-61, LAASSP Art. 57-58"""

    elif intencion == "abandono_obra":
        resultados = _motor.buscar("abandono obra contratista incumplimiento", max_resultados=6)
        respuesta = """🏗️ **Abandono de Obra / Incumplimiento del Contratista**

"""
        for r in resultados[:4]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """⚠️ **Acciones que puede tomar la dependencia:**
• Dar por rescindido el contrato
• Aplicar garantía de cumplimiento
• Cobrar penalizaciones por retraso
• Declarar al contratista no responsable
• Iniciar procedimiento de sanción

💡 **Documentos necesarios:**
• Acta de constatación de abandono
• Notificación al contratista
• Dictamen técnico de causa"""

    elif intencion == "recursos_inconformidad":
        resultados = _motor.buscar("inconformidad recurso revision protesta", max_resultados=6)
        respuesta = """📢 **Recursos de Inconformidad**

"""
        for r in resultados[:4]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """📋 **Tipos de recursos:**
• **Recurso de reconsideración** — Ante la misma dependencia
• **Recurso de revisión** — Ante instancia superior
• **Juicio de nulidad** — Vía jurisdiccional

⏱️ **Plazos:**
• Reconsideración: 15 días hábiles
• Revisión: 20 días hábiles

💡 **Requisitos:**
• Escrito fundamentado
• Pruebas documentales
• Pago de derechos (si aplica)"""

    elif intencion == "subcontratacion":
        resultados = _motor.buscar("subcontratacion tercerizacion delegacion", max_resultados=5)
        respuesta = """👷 **Subcontratación en Obra Pública**

"""
        for r in resultados[:3]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """⚠️ **Reglas importantes:**
• El contratista es responsable solidario
• Debe autorizarse por escrito
• No puede subcontratar más del 50% (generalmente)
• La dependencia debe conocer a los subcontratistas
• No se puede subcontratar la totalidad de la obra

💡 **Documentos requeridos:**
• Solicitud de autorización
• Datos del subcontratista
• Alcance de la subcontratación
• Garantías del subcontratista"""

    elif intencion == "transparencia":
        resultados = _motor.buscar("transparencia informacion publica compranet", max_resultados=5)
        respuesta = """📢 **Transparencia y Acceso a la Información**

"""
        for r in resultados[:3]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """📋 **Obligaciones de transparencia:**
• Publicar convocatoria en CompraNet
• Difundir bases de licitación
• Publicar fallo y contrato
• Informar avance de obra
• Publicar estimaciones y pagos

🌐 **Plataformas:**
• CompraNet (adquisiciones federales)
• Sistema de Portales de Obligaciones
• Diario Oficial de la Federación (DOF)

💡 **Base legal:** LOPSRM Art. 10, LAASSP Art. 10, Ley de Transparencia"""

    elif intencion == "supervision":
        resultados = _motor.buscar("supervision fiscalizacion vigilancia obra", max_resultados=5)
        respuesta = """👁️ **Supervisión y Fiscalización de Obra**

"""
        for r in resultados[:3]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """📋 **Funciones del supervisor:**
• Vigilar ejecución conforme a proyecto
• Validar estimaciones de avance
• Constatar calidad de materiales
• Autorizar modificaciones técnicas
• Levantar actas de hechos relevantes

⚠️ **El supervisor NO puede:**
• Modificar el contrato
• Autorizar pagos sin dictamen
• Aceptar trabajos fuera de especificaciones

💡 **Documentos:**
• Bitácora de obra
• Actas de junta de obra
• Informes mensuales de supervisión"""

    elif intencion == "plazos" and "monto" in parametros:
        # CORREGIDO (F-01): esta era una tercera copia independiente del
        # umbral 1M/50M (ni siquiera pasaba por _determinar_procedimiento_umbral
        # como las otras dos). Ahora usa el mismo motor real que el resto
        # del archivo -- una sola fuente de verdad para las 3 intenciones.
        monto = parametros["monto"]
        resultado = await _consultar_motor_juridico(db, monto)

        if not resultado["valido"]:
            respuesta = f"""📅 **Todavía no puedo calcular el plazo**

💰 **Monto:** ${monto:,.0f} MXN

⚠️ El procedimiento aplicable depende del presupuesto autorizado de tu dependencia (tabla del Anexo 9 del PEF, LOPSRM Art. 43 / LAASSP Art. 55), dato que no puedo extraer de un mensaje de chat con confianza.

💡 Usa la **calculadora de plazos** en el panel derecho: ahí puedes capturar el presupuesto autorizado de la dependencia y obtener el plazo exacto."""
        else:
            proc = _PROC_A_CLAVE.get(resultado["procedimiento"], resultado["procedimiento"])
            nom = _PROC_A_NOMBRE.get(proc, proc)
            plazos = _plazos_para(proc)
            advertencia = "\n\n⚠️ Cifras sin confirmar contra el Anexo 9 oficial -- ver advertencia en el resultado de /juridico/procedimiento." if resultado["es_candidato"] else ""

            respuesta = f"""📅 **Plazos para {nom}**

⏱️ **Total mínimo:** {plazos['total_minimo']} días hábiles

📖 **Base legal:** {resultado.get('fuente_umbral') or 'LOPSRM Art. 43 / LAASSP Art. 55 (Anexo 9 del PEF)'}

💡 **Nota:** Los plazos pueden ampliarse por:
• Junta de aclaraciones
• Modificaciones a las bases
• Circunstancias extraordinarias{advertencia}

Usa la **calculadora de plazos** en el panel derecho para fechas exactas."""

    elif intencion == "checklist" and "monto" in parametros:
        # CORREGIDO (F-01): cuarta copia independiente del mismo umbral
        # 1M/50M -- misma corrección que "plazos" arriba.
        monto = parametros["monto"]
        resultado = await _consultar_motor_juridico(db, monto)

        if not resultado["valido"]:
            respuesta = f"""✅ **Todavía no puedo generar el checklist exacto**

💰 **Monto:** ${monto:,.0f} MXN

⚠️ Sin el presupuesto autorizado de tu dependencia no puedo ubicar el tramo del Anexo 9 que determina si aplica adjudicación directa, invitación restringida o licitación pública -- y el checklist cambia según eso.

💡 Usa el **generador de checklist** en el panel derecho: ahí puedes capturar el presupuesto autorizado de la dependencia."""
        else:
            proc = _PROC_A_CLAVE.get(resultado["procedimiento"], resultado["procedimiento"])
            nom = _PROC_A_NOMBRE.get(proc, proc)

            respuesta = f"""✅ **Checklist — {nom}**

📋 **Documentos obligatorios:**
• ☑️ Dictamen técnico de la obra
• ☑️ Especificaciones técnicas completas
• ☑️ Presupuesto base con APU desglosados
• ☑️ Programa de obra (CPM/Gantt)
"""
            if proc != "adjudicacion_directa":
                respuesta += """• ☑️ Bases de licitación aprobadas
• ☑️ Publicación en CompraNet
• ☑️ Garantía de seriedad (5%)
• ☑️ Acta de apertura de proposiciones
• ☑️ Dictamen de comisión de evaluación
"""
            respuesta += """• ☑️ Acta de fallo firmada
• ☑️ Contrato de precios unitarios
• ☑️ Garantía de cumplimiento (piso desde LegalRule DB, p.ej. RLOPSRM Art. 91)
• ☑️ Garantía de vicios ocultos (5%)
"""
            if resultado["es_candidato"]:
                respuesta += "\n⚠️ El procedimiento usado para armar este checklist viene de cifras sin confirmar contra el Anexo 9 oficial."
            respuesta += "\n💡 Usa el **generador de checklist** en el panel derecho para marcar progreso."

    elif intencion == "garantias" and "monto" in parametros:
        monto = parametros["monto"]
        respuesta = f"""💰 **Garantías para ${monto:,.0f} MXN**

**Requeridas:**
• 🔒 **Seriedad:** PENDIENTE_REGLA (sin LegalRule en DB)
• 🛡️ **Cumplimiento:** consultar regla GARANTIA-CUMPLIMIENTO-OBRA-MIN10 en DB

**Adicionales:**
• 🔧 **Vicios ocultos:** PENDIENTE_REGLA (sin LegalRule en DB)
• 📋 **Buena calidad** (si aplica)

📖 **Base legal:** LOPSRM Art. 48, LAASSP Art. 46

💡 **Tipos de garantías aceptadas:**
• Fianza de fidelidad
• Póliza de cumplimiento
• Carta de crédito
• Depósito en efectivo"""

    elif intencion == "fase" and "fase" in parametros:
        resultados = _motor.buscar("", fase=parametros["fase"], max_resultados=6)
        fase_nombre = parametros["fase"].capitalize()
        respuesta = f"""📂 **Fase: {fase_nombre}**

"""
        if resultados:
            for r in resultados[:5]:
                respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:200]}...

"""
        else:
            # Búsqueda por categoría como fallback
            cat_map = {
                "planeacion": "procedimientos", "convocatoria": "procedimientos",
                "proposiciones": "procedimientos", "evaluacion": "evaluacion",
                "fallo": "procedimientos", "contrato": "contratos",
                "ejecucion": "pagos", "finiquito": "pagos",
            }
            cat = cat_map.get(parametros["fase"], parametros["fase"])
            resultados_cat = _motor.buscar_por_categoria(cat, 5)
            if resultados_cat:
                for r in resultados_cat[:5]:
                    respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:200]}...

"""
            else:
                respuesta += "No se encontraron artículos para esta fase en el corpus.\n"

    elif intencion == "ajuste_costos":
        resultados = _motor.buscar("INPC UMA ajuste costos precios", max_resultados=5)
        respuesta = """📈 **Ajuste de Costos (INPC/UMA)**

"""
        for r in resultados[:3]:
            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:250]}...

"""

        respuesta += """📋 **¿Cuándo aplica?**
• Circunstancias extraordinarias e imprevisibles
• Incremento en costos de insumos materiales
• Variación del INPC superior al 7%
• Cambio en el valor de la UMA

📊 **Fórmula:**
• Factor = INPC actual / INPC base
• Monto ajustado = Monto original × Factor

📄 **Documentos requeridos:**
• Solicitud formal del contratista
• Cotizaciones de insumos afectados
• Dictamen técnico de la dependencia
• Resolución de aprobación

💡 **Nota:** El ajuste NO aplica por retrasos imputables al contratista."""

    else:
        # CONSULTA GENERAL — Búsqueda inteligente en todo el corpus
        resultados = _motor.buscar(mensaje, max_resultados=8)

        if resultados:
            respuesta = f"""🔍 Encontré {len(resultados)} artículos relacionados con tu consulta:

"""
            for r in resultados[:5]:
                respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:220]}...

"""

            respuesta += "💡 ¿Quieres que profundice en alguno de estos artículos?"
        else:
            # Último intento: búsqueda por categoría.
            # BUG ORIGINAL: `for cat_id, cat_data in _motor.listar_categorias():`
            # -- listar_categorias() regresa una lista de dicts (cada uno con
            # su propia clave "id"), no pares (id, data), así que el
            # desempaquetado tronaba con ValueError en cuanto se llegaba aquí.
            for cat_data in _motor.listar_categorias():
                if any(p in mensaje_lower for p in cat_data['descripcion'].lower().split()):
                    resultados_cat = _motor.buscar_por_categoria(cat_data["id"], 5)
                    if resultados_cat:
                        respuesta = f"""🔍 Encontré artículos en la categoría "{cat_data['nombre']}":

"""
                        for r in resultados_cat[:5]:
                            respuesta += f"""📖 **{r['ley_nombre']} Art. {r['articulo']}**
{r['contenido'][:220]}...

"""
                        break
            else:
                respuesta = """🤔 No encontré información específica en el corpus legal.

**Intenta con:**
• Número de artículo (ej: "Artículo 40 LOPSRM")
• Términos más generales ("licitación", "contrato", "fallo")
• Preguntas sobre procedimientos ("¿qué procedimiento para X millones?")
• Temas específicos ("sanciones", "abandono", "subcontratación")

💡 **También puedo:**
• Comparar artículos entre leyes
• Calcular plazos según monto
• Generar checklists de requisitos
• Buscar por categoría temática

¿En qué más puedo ayudarte?"""

    return {
        "mensaje_usuario": mensaje,
        "intencion_detectada": intencion,
        "parametros": parametros,
        "respuesta": respuesta,
        "fuente": "corpus_legal_969_articulos",
        "sin_ia": True,
        "motor": "MotorBusquedaLegal v3.0",
    }
