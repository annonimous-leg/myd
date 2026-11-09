"""Offline review of original INEGI 2.0 JSON. No downloads, secrets or fallback rates."""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal

from app.schemas.indices_costos import CargaINEGIInput, ContratoINEGI, ObservacionIndiceCreate

MAX_ARCHIVO = 2 * 1024 * 1024
MAX_OBSERVACIONES = 5000


def _sin_duplicados(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('El JSON contiene claves duplicadas')
        result[key] = value
    return result


def _constante_invalida(_):
    raise ValueError('El JSON contiene una constante numérica inválida')


def revisar_archivo(archivo: bytes, contrato: ContratoINEGI, data: CargaINEGIInput) -> list[ObservacionIndiceCreate]:
    if not archivo or len(archivo) > MAX_ARCHIVO:
        raise ValueError('El archivo debe contener JSON UTF-8 y no exceder 2 MiB')
    if hashlib.sha256(archivo).hexdigest() != data.evidencia.sha256:
        raise ValueError('La huella declarada no coincide con los bytes del archivo')
    try:
        document = json.loads(archivo.decode('utf-8-sig'), object_pairs_hook=_sin_duplicados,
                              parse_float=Decimal, parse_int=Decimal, parse_constant=_constante_invalida)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Archivo JSON UTF-8 inválido o excesivamente anidado') from exc
    if not isinstance(document, dict) or not isinstance(document.get('Series'), list) or len(document['Series']) != 1:
        raise ValueError('Se requiere exactamente una serie original por archivo')
    if set(document) - {'Header', 'Series'}:
        raise ValueError('Campos de documento desconocidos; revisar el formato antes de cargar')
    serie = document['Series'][0]
    if not isinstance(serie, dict):
        raise ValueError('Estructura de serie inválida')
    expected = {'INDICADOR': contrato.indicador, 'FREQ': contrato.frecuencia,
                'UNIT': contrato.unidad, 'UNIT_MULT': contrato.multiplicador,
                'TOPIC': contrato.tema, 'SOURCE': contrato.fuente, 'NOTE': contrato.notas,
                'STATUS': contrato.estatus_serie, 'LASTUPDATE': data.ultima_actualizacion}
    if set(serie) != set(expected) | {'OBSERVATIONS'}:
        raise ValueError('Campos de serie desconocidos o ausentes; revisar el formato')
    for field, value in expected.items():
        if serie.get(field) != value:
            raise ValueError(f'Metadato {field} distinto del contrato revisado')
    observations = serie.get('OBSERVATIONS')
    if not isinstance(observations, list) or not 1 <= len(observations) <= MAX_OBSERVACIONES:
        raise ValueError('Cantidad de observaciones inválida; máximo 5000')
    result, seen = [], set()
    for i, observation in enumerate(observations):
        if not isinstance(observation, dict):
            raise ValueError(f'Observación {i} inválida')
        if set(observation) != {'TIME_PERIOD', 'OBS_VALUE', 'OBS_EXCEPTION', 'OBS_STATUS', 'OBS_SOURCE', 'OBS_NOTE', 'COBER_GEO'}:
            raise ValueError(f'Observación {i}: campos desconocidos o ausentes')
        period = observation.get('TIME_PERIOD')
        if not isinstance(period, str) or not re.fullmatch(r'\d{4}[-/]\d{2}', period):
            raise ValueError(f'Observación {i}: se requiere un periodo mensual YYYY/MM o YYYY-MM')
        try:
            mes = date(int(period[:4]), int(period[5:]), 1)
        except ValueError as exc:
            raise ValueError(f'Observación {i}: mes inválido') from exc
        if mes in seen:
            raise ValueError('El archivo repite un mes, aunque cambie su valor o estado')
        seen.add(mes)
        if not data.mes_inicio <= mes <= data.mes_fin:
            continue
        for field, value in {'COBER_GEO': contrato.cobertura, 'OBS_STATUS': contrato.estatus_observacion,
                             'OBS_SOURCE': contrato.fuente_observacion, 'OBS_NOTE': contrato.notas_observacion,
                             'OBS_EXCEPTION': ''}.items():
            if observation.get(field) != value:
                raise ValueError(f'Observación {i}: {field} incompatible con la revisión')
        value = observation.get('OBS_VALUE')
        if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
            raise ValueError(f'Observación {i}: nivel ausente o inválido')
        # Original bytes are retained once, not copied into every snapshot.
        evidence = data.evidencia.model_copy(update={'localizador': f'Series[0].OBSERVATIONS[{i}]; TIME_PERIOD={period}'})
        try:
            result.append(ObservacionIndiceCreate(serie_id=data.serie_id, medida='NIVEL', mes=mes,
                          valor=value, publicado_el=data.publicado_el, evidencia=evidence))
        except ValueError as exc:
            raise ValueError(f'Observación {i}: nivel o fecha de publicación inválidos') from exc
    expected_count = (data.mes_fin.year - data.mes_inicio.year) * 12 + data.mes_fin.month - data.mes_inicio.month + 1
    if len(result) != expected_count:
        raise ValueError('Faltan meses del intervalo solicitado; no se interpolan ni completan con inflación global')
    return sorted(result, key=lambda row: row.mes)
