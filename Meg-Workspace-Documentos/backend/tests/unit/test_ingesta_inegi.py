"""Synthetic API-shaped fixtures; codes and levels are deliberately NOT official."""
import hashlib
import json
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engines.costos.ingesta_inegi import revisar_archivo, MAX_ARCHIVO
from app.schemas.indices_costos import CargaINEGIInput, ContratoINEGI
from app.schemas.indices_costos import EvidenciaIndice


def contrato_controlado():
    return ContratoINEGI(indicador='999999999', frecuencia='TEST-M', unidad='TEST-INDEX',
        multiplicador='TEST-1', tema='TEST-MATERIAL', fuente='TEST-SOURCE', notas='', estatus_serie='',
        cobertura='TEST-NATIONAL', estatus_observacion='TEST-DEFINITIVE', fuente_observacion='', notas_observacion='',
        periodicidad_revisada='MENSUAL', medida_revisada='NIVEL_INDICE', escala_revisada='UNIDAD',
        alcance_revisado='MATERIAL', evidencia_metadatos={'url': 'https://example.invalid/metadata.json',
        'sha256': 'a' * 64, 'localizador': 'CONTROLADO, NO OFICIAL'})


def documento_controlado():
    return {'Header': {'Name': 'CONTROLADO, NO OFICIAL'}, 'Series': [{
        'INDICADOR': '999999999', 'FREQ': 'TEST-M', 'UNIT': 'TEST-INDEX', 'UNIT_MULT': 'TEST-1',
        'TOPIC': 'TEST-MATERIAL', 'SOURCE': 'TEST-SOURCE', 'NOTE': '', 'STATUS': '', 'LASTUPDATE': 'CONTROLLED-2020-03',
        'OBSERVATIONS': [dict(TIME_PERIOD=mes, OBS_VALUE=valor, OBS_EXCEPTION='', OBS_STATUS='TEST-DEFINITIVE',
                             OBS_SOURCE='', OBS_NOTE='', COBER_GEO='TEST-NATIONAL')
                             for mes, valor in [('2020/01', '100.12345678901234567'), ('2020/02', '110.76543210987654321')]]}]}


def datos_archivo(archivo, serie_id=None):
    return CargaINEGIInput(serie_id=serie_id or uuid4(), mes_inicio='2020-01-01', mes_fin='2020-02-01',
        publicado_el='2020-03-10', ultima_actualizacion='CONTROLLED-2020-03',
        evidencia={'url': 'https://www.inegi.org.mx/programas/inpp/2019a/',
        'sha256': hashlib.sha256(archivo).hexdigest(), 'localizador': 'CONTROLADO, NO OFICIAL'})


def test_preserva_decimales_y_orden_original_para_evidencia():
    doc = documento_controlado()
    doc['Series'][0]['OBSERVATIONS'].reverse()
    archivo = json.dumps(doc).encode()
    result = revisar_archivo(archivo, contrato_controlado(), datos_archivo(archivo))
    assert result[0].valor == Decimal('100.12345678901234567')
    assert result[1].valor == Decimal('110.76543210987654321')
    assert 'OBSERVATIONS[1]' in result[0].evidencia.localizador


@pytest.mark.parametrize('campo,valor', [('FREQ','TEST-YEARLY'), ('UNIT','PERCENT'), ('UNIT_MULT','1000'),
    ('INDICADOR','OTHER'), ('TOPIC','TEST-AGGREGATE'), ('SOURCE','OTHER'), ('NOTE','NEW-METHODOLOGY'),
    ('STATUS','PRELIMINARY'), ('LASTUPDATE','OTHER')])
def test_metadatos_incompatibles(campo, valor):
    doc = documento_controlado()
    doc['Series'][0][campo] = valor
    archivo = json.dumps(doc).encode()
    with pytest.raises(ValueError):
        revisar_archivo(archivo, contrato_controlado(), datos_archivo(archivo))


@pytest.mark.parametrize('campo,valor', [('OBS_VALUE',''), ('OBS_VALUE',None), ('OBS_VALUE',True),
    ('OBS_VALUE','0'), ('OBS_VALUE','-1'), ('OBS_VALUE','NaN'), ('OBS_VALUE','Infinity'),
    ('OBS_VALUE','1.123456789012345678901'), ('TIME_PERIOD','2020'), ('TIME_PERIOD','2020/13'),
    ('TIME_PERIOD','2020/01/01'), ('OBS_EXCEPTION','MISSING'), ('OBS_STATUS','ESTIMATE'),
    ('OBS_SOURCE','OTHER'), ('OBS_NOTE','FORECAST'), ('COBER_GEO','OTHER')])
def test_observacion_incompatible_no_produce_lote_parcial(campo, valor):
    doc = documento_controlado()
    doc['Series'][0]['OBSERVATIONS'][1][campo] = valor
    archivo = json.dumps(doc).encode()
    with pytest.raises(ValueError):
        revisar_archivo(archivo, contrato_controlado(), datos_archivo(archivo))


@pytest.mark.parametrize('modo', ['duplicado','hueco','multiserie','campo_desconocido'])
def test_estructura_y_cobertura(modo):
    doc = documento_controlado()
    if modo == 'duplicado': doc['Series'][0]['OBSERVATIONS'].append(doc['Series'][0]['OBSERVATIONS'][0])
    if modo == 'hueco': doc['Series'][0]['OBSERVATIONS'].pop()
    if modo == 'multiserie': doc['Series'].append(doc['Series'][0])
    if modo == 'campo_desconocido': doc['Series'][0]['METHOD'] = 'OTHER'
    archivo = json.dumps(doc).encode()
    with pytest.raises(ValueError):
        revisar_archivo(archivo, contrato_controlado(), datos_archivo(archivo))


@pytest.mark.parametrize('archivo', [b'{"Series":[],"Series":[]}', b'{"Series":NaN}', b'[]',
                                   b'\xff', b'{', b'x' * (MAX_ARCHIVO + 1)],
                         ids=['duplicate_keys', 'nan_value', 'top_level_array', 'invalid_utf8',
                              'truncated_json', 'oversized_payload'])
def test_json_cerrado_y_limite(archivo):
    with pytest.raises(ValueError):
        revisar_archivo(archivo, contrato_controlado(), datos_archivo(archivo))


def test_huella_distinta_y_publicacion_anticipada():
    archivo = json.dumps(documento_controlado()).encode()
    data = datos_archivo(archivo)
    with pytest.raises(ValueError):
        revisar_archivo(archivo + b' ', contrato_controlado(), data)
    data.publicado_el = data.mes_fin
    with pytest.raises(ValueError):
        revisar_archivo(archivo, contrato_controlado(), data)


@pytest.mark.parametrize('url', ['https://www.inegi.org.mx/app/api/indicadores/2.0/PRIVATE-TOKEN',
    'https://inegi.org.mx/app/api/indicadores/2.0/PRIVATE-TOKEN',
    'https://www.inegi.org.mx/%61pp/api/indicadores/2.0/PRIVATE-TOKEN',
    'https://www.inegi.org.mx/programas/inpp/2019a/?token=PRIVATE-TOKEN'])
def test_no_publica_token_inegi_en_ninguna_evidencia(url):
    with pytest.raises(ValueError):
        EvidenciaIndice(url=url, sha256='a' * 64, localizador='CONTROLADO')
