# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de validación de expedientes (checks documentales/normativos).

CONTEXTO: app/models/validador.py define ValidacionExpediente y
CheckValidacion como un catálogo de checks reutilizables y orientados a
datos (cada CheckValidacion guarda en `logica` un {"tipo", "parametros"}
en vez de código), pero en ningún lugar del backend existía el motor que
realmente interpretara esa `logica` y la corriera contra un expediente
real -- los modelos existían, el ejecutor no. Este módulo es ese
ejecutor.

Tipos de check soportados (logica["tipo"]):
  - documento_existe:   {tipo_documento, requerido=True, min_cantidad=1}
      ¿Existe al menos `min_cantidad` documento(s) de ese tipo, en
      DocumentoCDE o en Documento (legado), asociados al expediente?
  - rango_numerico:     {campo, min=None, max=None}
      ¿El campo numérico del expediente está dentro de [min, max]?
  - campo_no_vacio:     {campo}
      ¿El campo del expediente no es None/"" ?
  - valor_en_catalogo:  {campo, valores_permitidos: [...]}
      ¿El valor del campo está en la lista permitida?
  - regex_formato:      {campo, patron, descripcion_formato=None}
      ¿El campo (como string) coincide con el patrón regex dado?

Cada check tiene una `severidad` (BLOQUEANTE/ALTA/MEDIA/BAJA/INFORMATIVA,
ver CheckValidacion.severidad) que determina cómo pesa en el resultado
final:
  - Si falla algún check BLOQUEANTE  -> ValidacionExpediente.estado = RECHAZADA
  - Si falla algún check no bloqueante (y ninguno bloqueante falló)
                                     -> estado = CON_OBSERVACIONES
  - Si todos los checks evaluables pasan -> estado = APROBADA
El score (0-100) es un promedio ponderado por severidad de los checks que
sí cuentan para el score (todas menos INFORMATIVA).
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

PESO_SEVERIDAD: Dict[str, float] = {
    "BLOQUEANTE": 4.0,
    "ALTA": 3.0,
    "MEDIA": 2.0,
    "BAJA": 1.0,
    "INFORMATIVA": 0.0,
}

TIPOS_CHECK_SOPORTADOS = (
    "documento_existe",
    "rango_numerico",
    "campo_no_vacio",
    "valor_en_catalogo",
    "regex_formato",
)


@dataclass
class ResultadoCheck:
    """Resultado de correr un CheckValidacion contra un expediente."""

    check_id: str
    codigo: str
    nombre: str
    categoria: str
    severidad: str
    estado: str  # APROBADO | RECHAZADO | ERROR_CONFIGURACION
    detalle: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "codigo": self.codigo,
            "nombre": self.nombre,
            "categoria": self.categoria,
            "severidad": self.severidad,
            "estado": self.estado,
            "detalle": self.detalle,
        }


@dataclass
class ReporteValidacionExpediente:
    resultados: List[ResultadoCheck] = field(default_factory=list)
    estado: str = "APROBADA"
    score: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resultados": [r.to_dict() for r in self.resultados],
            "estado": self.estado,
            "score": self.score,
        }


def _obtener_campo(expediente: Any, campo: str):
    """Lee un atributo del expediente por nombre, devolviendo None si no existe."""
    return getattr(expediente, campo, None)


def _documentos_del_expediente(expediente: Any) -> List[Any]:
    """Reúne documentos de ambos modelos documentales (DocumentoCDE y el
    Documento legado) que puedan colgar del expediente. Cualquiera de los
    dos puede estar poblado según qué parte del sistema los haya cargado,
    así que se consultan ambos en vez de asumir uno solo."""
    docs: List[Any] = []
    docs.extend(getattr(expediente, "documentos_cde", None) or [])
    docs.extend(getattr(expediente, "documentos", None) or [])
    return docs


def _tipo_documento_de(doc: Any) -> Optional[str]:
    """DocumentoCDE.tipo es un TipoDocumento (Enum); Documento.tipo_documental
    es texto libre. Se normaliza a string en mayúsculas para comparar ambos
    de forma homogénea."""
    valor = getattr(doc, "tipo", None)
    if valor is None:
        valor = getattr(doc, "tipo_documental", None)
    if valor is None:
        return None
    valor = getattr(valor, "value", valor)  # Enum -> str si aplica
    return str(valor).upper()


def _estado_documento_es_vigente(doc: Any) -> bool:
    """Un documento ARCHIVADO/OBSOLETO no debería contar como "presente"
    para fines de cumplimiento -- se busca su reemplazo vigente."""
    estado = getattr(doc, "estado", None)
    estado = getattr(estado, "value", estado)
    if estado is None:
        return True  # Documento legado sin campo 'estado': se asume vigente.
    return str(estado).upper() not in ("ARCHIVADO", "OBSOLETO")


class MotorValidacionExpediente:
    """Ejecuta un catálogo de CheckValidacion contra un ExpedienteObra real."""

    def ejecutar(
        self,
        expediente: Any,
        checks: Sequence[Any],
    ) -> ReporteValidacionExpediente:
        reporte = ReporteValidacionExpediente()
        documentos = _documentos_del_expediente(expediente)

        peso_total = 0.0
        peso_logrado = 0.0
        hay_falla_bloqueante = False
        hay_falla_no_bloqueante = False

        for check in sorted(checks, key=lambda c: getattr(c, "orden", 0)):
            resultado = self._ejecutar_check(check, expediente, documentos)
            reporte.resultados.append(resultado)

            severidad = (check.severidad or "MEDIA").upper()
            peso = PESO_SEVERIDAD.get(severidad, 2.0)

            if resultado.estado == "RECHAZADO":
                if severidad == "BLOQUEANTE":
                    hay_falla_bloqueante = True
                else:
                    hay_falla_no_bloqueante = True

            if peso > 0:
                peso_total += peso
                if resultado.estado == "APROBADO":
                    peso_logrado += peso
                elif resultado.estado == "ERROR_CONFIGURACION":
                    # Un check mal configurado no debe penalizar como si
                    # fuera un incumplimiento real; se excluye del score.
                    peso_total -= peso

        if hay_falla_bloqueante:
            reporte.estado = "RECHAZADA"
        elif hay_falla_no_bloqueante:
            reporte.estado = "CON_OBSERVACIONES"
        else:
            reporte.estado = "APROBADA"

        reporte.score = round(100 * peso_logrado / peso_total) if peso_total > 0 else 100
        return reporte

    def _ejecutar_check(self, check: Any, expediente: Any, documentos: List[Any]) -> ResultadoCheck:
        base = dict(
            check_id=str(check.id),
            codigo=check.codigo,
            nombre=check.nombre,
            categoria=check.categoria,
            severidad=(check.severidad or "MEDIA").upper(),
        )
        logica = check.logica or {}
        tipo = logica.get("tipo")
        parametros = logica.get("parametros") or {}

        try:
            if tipo == "documento_existe":
                return self._check_documento_existe(base, parametros, documentos, check)
            if tipo == "rango_numerico":
                return self._check_rango_numerico(base, parametros, expediente, check)
            if tipo == "campo_no_vacio":
                return self._check_campo_no_vacio(base, parametros, expediente, check)
            if tipo == "valor_en_catalogo":
                return self._check_valor_en_catalogo(base, parametros, expediente, check)
            if tipo == "regex_formato":
                return self._check_regex_formato(base, parametros, expediente, check)
            return ResultadoCheck(
                **base,
                estado="ERROR_CONFIGURACION",
                detalle=(
                    f"Tipo de check '{tipo}' no reconocido. Tipos soportados: "
                    f"{', '.join(TIPOS_CHECK_SOPORTADOS)}."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - aislar un check roto del resto de la corrida
            return ResultadoCheck(
                **base,
                estado="ERROR_CONFIGURACION",
                detalle=f"Error evaluando el check '{check.codigo}': {exc}",
            )

    # -- Implementaciones de cada tipo de check --------------------------

    def _check_documento_existe(self, base, parametros, documentos, check) -> ResultadoCheck:
        tipo_documento = str(parametros.get("tipo_documento", "")).upper()
        requerido = bool(parametros.get("requerido", True))
        min_cantidad = int(parametros.get("min_cantidad", 1))

        if not tipo_documento:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle="Falta 'tipo_documento' en los parámetros del check.")

        coincidencias = [
            d for d in documentos
            if _tipo_documento_de(d) == tipo_documento and _estado_documento_es_vigente(d)
        ]
        cantidad = len(coincidencias)

        if cantidad >= min_cantidad:
            detalle = (check.mensaje_exito or
                       f"Se encontraron {cantidad} documento(s) vigente(s) de tipo {tipo_documento}"
                       f" (mínimo requerido: {min_cantidad}).")
            return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)

        if not requerido:
            detalle = (f"No se encontró documento de tipo {tipo_documento}, pero el check no es "
                       f"obligatorio (requerido=false); se registra como informativo.")
            return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)

        detalle = (check.mensaje_error or
                   f"Se requieren {min_cantidad} documento(s) vigente(s) de tipo {tipo_documento}, "
                   f"se encontraron {cantidad}.")
        return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)

    def _check_rango_numerico(self, base, parametros, expediente, check) -> ResultadoCheck:
        campo = parametros.get("campo")
        if not campo:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle="Falta 'campo' en los parámetros del check.")
        valor = _obtener_campo(expediente, campo)
        if valor is None:
            return ResultadoCheck(
                **base, estado="RECHAZADO",
                detalle=f"El campo '{campo}' no tiene valor capturado en el expediente.",
            )
        try:
            valor_num = float(valor)
        except (TypeError, ValueError):
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle=f"El campo '{campo}' no es numérico (valor: {valor!r}).")

        minimo = parametros.get("min")
        maximo = parametros.get("max")
        if minimo is not None and valor_num < float(minimo):
            detalle = (check.mensaje_error or
                       f"{campo}={valor_num} está por debajo del mínimo permitido ({minimo}).")
            return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)
        if maximo is not None and valor_num > float(maximo):
            detalle = (check.mensaje_error or
                       f"{campo}={valor_num} excede el máximo permitido ({maximo}).")
            return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)

        detalle = check.mensaje_exito or f"{campo}={valor_num} está dentro del rango permitido."
        return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)

    def _check_campo_no_vacio(self, base, parametros, expediente, check) -> ResultadoCheck:
        campo = parametros.get("campo")
        if not campo:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle="Falta 'campo' en los parámetros del check.")
        valor = _obtener_campo(expediente, campo)
        vacio = valor is None or (isinstance(valor, str) and valor.strip() == "")
        if vacio:
            detalle = check.mensaje_error or f"El campo '{campo}' está vacío."
            return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)
        detalle = check.mensaje_exito or f"El campo '{campo}' está capturado."
        return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)

    def _check_valor_en_catalogo(self, base, parametros, expediente, check) -> ResultadoCheck:
        campo = parametros.get("campo")
        permitidos = parametros.get("valores_permitidos") or []
        if not campo or not permitidos:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle="Faltan 'campo' o 'valores_permitidos' en los parámetros.")
        valor = _obtener_campo(expediente, campo)
        valor_norm = getattr(valor, "value", valor)
        permitidos_norm = [getattr(v, "value", v) for v in permitidos]
        if valor_norm in permitidos_norm:
            detalle = check.mensaje_exito or f"{campo}={valor_norm} es un valor permitido."
            return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)
        detalle = (check.mensaje_error or
                   f"{campo}={valor_norm!r} no está en el catálogo permitido {permitidos_norm}.")
        return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)

    def _check_regex_formato(self, base, parametros, expediente, check) -> ResultadoCheck:
        campo = parametros.get("campo")
        patron = parametros.get("patron")
        if not campo or not patron:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle="Faltan 'campo' o 'patron' en los parámetros del check.")
        valor = _obtener_campo(expediente, campo)
        if valor is None:
            return ResultadoCheck(**base, estado="RECHAZADO",
                                   detalle=f"El campo '{campo}' no tiene valor capturado.")
        try:
            coincide = re.fullmatch(patron, str(valor)) is not None
        except re.error as exc:
            return ResultadoCheck(**base, estado="ERROR_CONFIGURACION",
                                   detalle=f"Patrón regex inválido en el check: {exc}")
        if coincide:
            detalle = check.mensaje_exito or f"'{valor}' cumple el formato esperado."
            return ResultadoCheck(**base, estado="APROBADO", detalle=detalle)
        descripcion_formato = parametros.get("descripcion_formato")
        detalle = check.mensaje_error or (
            f"'{valor}' no cumple el formato esperado"
            + (f" ({descripcion_formato})." if descripcion_formato else f" (patrón: {patron}).")
        )
        return ResultadoCheck(**base, estado="RECHAZADO", detalle=detalle)


# ---------------------------------------------------------------------------
# Catálogo por defecto: checks razonables listos para usarse out-of-the-box
# (ejemplo Enterprise, no un placeholder vacío). Se usa desde
# ValidadorExpedienteService.sembrar_checks_default() -- es idempotente por
# `codigo` único, así que sembrar dos veces no duplica nada.
# ---------------------------------------------------------------------------
CHECKS_DEFAULT: List[Dict[str, Any]] = [
    {
        "codigo": "EXP-DOC-CONVOCATORIA",
        "nombre": "Convocatoria presente",
        "descripcion": "El expediente debe tener la convocatoria publicada.",
        "categoria": "DOCUMENTAL",
        "severidad": "BLOQUEANTE",
        "orden": 10,
        "logica": {"tipo": "documento_existe", "parametros": {"tipo_documento": "CONVOCATORIA", "requerido": True}},
    },
    {
        "codigo": "EXP-DOC-BASES",
        "nombre": "Bases de licitación presentes",
        "descripcion": "El expediente debe tener las bases de licitación.",
        "categoria": "DOCUMENTAL",
        "severidad": "BLOQUEANTE",
        "orden": 20,
        "logica": {"tipo": "documento_existe", "parametros": {"tipo_documento": "BASES", "requerido": True}},
    },
    {
        "codigo": "EXP-DOC-CONTRATO",
        "nombre": "Contrato presente",
        "descripcion": "El expediente debe tener el contrato formalizado.",
        "categoria": "DOCUMENTAL",
        "severidad": "ALTA",
        "orden": 30,
        "logica": {"tipo": "documento_existe", "parametros": {"tipo_documento": "CONTRATO", "requerido": True}},
    },
    {
        "codigo": "EXP-FIN-MONTO-POSITIVO",
        "nombre": "Monto de contrato válido",
        "descripcion": "El monto del contrato debe ser mayor a cero y menor a 5,000 millones MXN.",
        "categoria": "FINANCIERA",
        "severidad": "BLOQUEANTE",
        "orden": 40,
        "logica": {"tipo": "rango_numerico", "parametros": {"campo": "monto_contrato", "min": 0.01, "max": 5_000_000_000}},
    },
    {
        "codigo": "EXP-TEMP-PLAZO-RAZONABLE",
        "nombre": "Plazo de ejecución razonable",
        "descripcion": "El plazo en días debe estar entre 1 y 1,825 (5 años).",
        "categoria": "TEMPORAL",
        "severidad": "MEDIA",
        "orden": 50,
        "logica": {"tipo": "rango_numerico", "parametros": {"campo": "plazo_dias", "min": 1, "max": 1825}},
    },
    {
        "codigo": "EXP-NORM-RESPONSABLE-TECNICO",
        "nombre": "Responsable técnico asignado",
        "descripcion": "El expediente debe tener un responsable técnico capturado.",
        "categoria": "NORMATIVA",
        "severidad": "ALTA",
        "orden": 60,
        "logica": {"tipo": "campo_no_vacio", "parametros": {"campo": "responsable_tecnico"}},
    },
    {
        "codigo": "EXP-NORM-ORGANO-CAPTURADO",
        "nombre": "Órgano contratante capturado",
        "descripcion": "El expediente debe indicar el órgano/dependencia contratante.",
        "categoria": "NORMATIVA",
        "severidad": "BLOQUEANTE",
        "orden": 70,
        "logica": {"tipo": "campo_no_vacio", "parametros": {"campo": "organo"}},
    },
    {
        "codigo": "EXP-DOC-ACTA-FALLO",
        "nombre": "Acta de fallo presente",
        "descripcion": "Debe existir el acta que resuelve la licitación (fallo).",
        "categoria": "DOCUMENTAL",
        "severidad": "INFORMATIVA",
        "orden": 80,
        "logica": {"tipo": "documento_existe", "parametros": {"tipo_documento": "FALLA", "requerido": False}},
    },
]
