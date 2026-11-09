"""Extract SICT DGST source editions without executing embedded content.

Only the published catalogue columns are prices; summary tables and examples
are excluded. Original pages and row coordinates remain in the private package.
No inflation, VAT conversion, regional factor or component APU is invented.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pdfplumber

from app.services.catalogo_package import SCHEMA, digest

REVISION = 'VALIDADO_ESTRUCTURAL'
SOURCE_URL = 'https://micrs.sct.gob.mx/infraestructura/direccion-general-de-servicios-tecnicos/tabulador/'
PROFILES = {
    'parametricos': {'title': 'TABULADOR DE COSTOS PARAMÉTRICOS', 'start': 42,
                    'pattern': r'(?=[A-Z0-9]*[0-9])[A-Z][A-Z0-9]{4,10}', 'code_end': 110, 'description_end': 444},
    'servicios': {'title': 'SERVICIOS RELACIONADOS CON LA OBRA', 'start': 43,
                  'pattern': r'[A-Z]{2}\d{4}\.\d{2,4}', 'code_end': 110, 'description_end': 452},
    'construccion': {'title': 'TABULADOR A COSTO DIRECTO PARA LA CONSTRUCCIÓN', 'start': 87,
                    'pattern': r'\d{3}\.\d{2}\.\d{4}', 'code_end': 146, 'description_end': 469},
    'maquinaria': {'title': 'TABULADOR DE COSTOS PARA MAQUINARIA', 'start': 12,
                  'pattern': r'\d{4}', 'code_end': 140, 'description_end': 329},
}
MONEY = re.compile(r'\$(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?')


def row(table, **values):
    result = dict.fromkeys(SCHEMA[table], '')
    for field in ('metadatos', 'aplicabilidad', 'registro_bruto', 'evidencia', 'efecto_normalizado'):
        if field in result: result[field] = '{}'
    if 'estado_revision' in result: result['estado_revision'] = REVISION
    result.update({k: str(v) for k, v in values.items()})
    return result


def joined(words):
    # Group text by its printed baseline; PDF stream order is not row order.
    lines = []
    for w in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not lines or abs(lines[-1][0] - w['top']) > 2:
            lines.append((w['top'], []))
        lines[-1][1].append(w)
    return ' '.join(' '.join(w['text'] for w in sorted(ws, key=lambda w: w['x0'])) for _, ws in lines)


def road_scope(description):
    # Matching tolerates PDF spacing/diacritics; the original text is never
    # rewritten. A mixed material or an unrelated structure has no safe FIC.
    normalized = unicodedata.normalize('NFKD', description.upper())
    compact = ''.join(c for c in normalized if not c.isspace() and not unicodedata.combining(c))
    if not compact.startswith('CARRETERA'):
        return ''
    materials = [scope for token, scope in (
        ('ASFALTICA', 'CARRETERA_ASFALTICA'),
        ('CONCRETOHIDRAULICO', 'CARRETERA_HIDRAULICA'),
    ) if token in compact]
    return materials[0] if len(materials) == 1 else ''


def extract_page(words, profile, page_number):
    """Return every code anchor, including incomplete rows, for review."""
    anchors = sorted((w for w in words if 95 < w['top'] < 735
        and w['x0'] < profile['code_end'] and re.fullmatch(profile['pattern'], w['text'])),
        key=lambda w: w['top'])
    result = []
    for i, a in enumerate(anchors):
        stop = anchors[i + 1]['top'] - 2 if i + 1 < len(anchors) else 730
        start = a['top'] - 2
        # Headings between concepts end the previous description.
        headings = [w['top'] for w in words if a['top'] + 3 < w['top'] < stop
                    and w['x0'] < profile['code_end'] and re.fullmatch(r'\d+(?:\.\d+)*', w['text'])]
        if headings: stop = min(stop, min(headings) - 2)
        band = [w for w in words if start <= w['top'] < stop]
        desc = joined([w for w in band if profile['code_end'] <= w['x0'] < profile['description_end']])
        same = [w for w in words if abs(w['top'] - a['top']) < 3]
        prices = sorted((w for w in same if w['x0'] >= profile['description_end'] and MONEY.fullmatch(w['text'])), key=lambda w: w['x0'])
        unit_words = [w for w in same if profile['description_end'] <= w['x0'] < 503
                      and not MONEY.fullmatch(w['text'])]
        result.append({'code': a['text'], 'description': desc, 'unit': joined(unit_words),
            'prices': prices, 'page': page_number,
            'bbox': [a['x0'], start, max((w['x1'] for w in band), default=a['x1']), stop],
            'raw_words': [{k: w[k] for k in ('text', 'x0', 'top', 'x1', 'bottom')} for w in band]})
    return result


def extract_source(pdf: Path, kind: str):
    profile = PROFILES[kind]
    records = {t: [] for t in SCHEMA}
    source_sha = digest(pdf)
    sid = f'SICT_DGST_{kind.upper()}_{source_sha[:16]}'
    with pdfplumber.open(pdf) as doc:
        preface = ' '.join((p.extract_text() or '') for p in doc.pages[:3])
        normalized = re.sub(r'\s+', ' ', preface).upper()
        if profile['title'] not in normalized or '2026' not in normalized:
            raise ValueError('La fuente no corresponde al tabulador SICT 2026 seleccionado')
        vigencia = re.search(r'(?:partir del|desde)\s+1\s+de\s+(febrero|julio)(?:\s+de)?\s+2026', preface, re.I)
        if not vigencia: raise ValueError('Vigencia documental SICT no identificada')
        effective = date(2026, 2 if vigencia[1].lower() == 'febrero' else 7, 1).isoformat()
        # July construction was checked against its 485-page original: the
        # catalogue retains these columns, but changes prices and pagination.
        # Other July tabulators have not been verified with this profile.
        if effective == '2026-07-01' and kind != 'construccion':
            raise ValueError(f'La edición de julio de {kind} requiere verificar su estructura')
        records['fuente'].append(row('fuente', fuente_id=sid, familia='SICT_DGST_2026',
            titulo=f'SICT DGST {kind} 2026', archivo_original=pdf.name, sha256=source_sha, paginas=len(doc.pages),
            editor='SICT / DGST', edicion=effective, fecha_vigencia=effective, moneda='MXN',
            tipo_fuente='TABULADOR_COSTO_DIRECTO', alcance_geografico='México; aplicar condiciones documentales',
            base_geografica='Fuente original; sin ajuste regional automático', naturaleza_uso='REFERENCIA_COSTO_DIRECTO',
            notas_aplicacion='Sin actualización por inflación ni APU de componentes inventados',
            metadatos=json.dumps({'url_inventario_oficial': SOURCE_URL, 'perfil': kind, 'extractor': 'sict-dgst-v3'}, ensure_ascii=False)))
        seen = Counter()
        for number, page in enumerate(doc.pages, 1):
            text = page.extract_text() or ''
            records['pagina_fuente'].append(row('pagina_fuente', fuente_id=sid, pagina_pdf=number,
                etiqueta_impresa=str(number), texto_bruto=text, texto_sha256=hashlib.sha256(text.encode()).hexdigest(),
                metodo_extraccion='pdfplumber; texto y coordenadas originales', caracteres=len(text), advertencias='[]'))
            if number >= profile['start']:
                for ordinal, item in enumerate(extract_page(page.extract_words(), profile, number), 1):
                    # Section headings have a code but no monetary columns.
                    # Keep them as application rules, never as an invented zero price.
                    if not item['prices']:
                        records['regla_aplicacion'].append(row('regla_aplicacion', regla_id=f'{sid}:heading:{number}:{ordinal}:{item["code"]}',
                            fuente_id=sid, pagina_pdf=number, categoria='ENCABEZADO_O_FILA_SIN_PRECIO', titulo=item['code'],
                            texto=item['description'], estado_revision='INFORMATIVO'))
                        continue
                    seen[item['code']] += 1
                    if kind == 'parametricos':
                        description = item['description'].upper()
                        scope = road_scope(description)
                        complete = len(item['prices']) == 1 and item['unit'] and description and scope
                        records['modelo_parametrico'].append(row('modelo_parametrico',
                            modelo_id=f'{sid}:{number}:{ordinal}:{item["code"]}', fuente_id=sid, codigo=item['code'],
                            nombre=item['description'], nombre_bruto=item['description'], tipo_construccion=scope,
                            medida_base='1', unidad_medida_base=item['unit'], costo_por_unidad=item['prices'][0]['text'][1:].replace(',', ''),
                            moneda='MXN', pagina_inicio=number, pagina_fin=number, confianza='1',
                            estado_revision=REVISION if complete else 'REQUIERE_REVISION',
                            aplicabilidad=json.dumps({'no_es_APU_contractual': True, 'fic_especialidad': scope,
                                'acarreo_incluido_km': 10, 'requiere_revision_alcance': True}), registro_bruto=json.dumps(item)))
                        continue
                    variants = ['ACTIVO', 'ESPERA', 'RESERVA'] if kind == 'maquinaria' else ['DIRECTO']
                    expected = 5 if kind == 'maquinaria' else 1
                    columns = {}
                    if kind == 'maquinaria':
                        # Right edges align with the column header. A missing
                        # acquisition value must never shift Activo to Espera.
                        for value in item['prices']:
                            key = ('VA_USD' if value['x1'] < 390 else 'VA_MXN' if value['x1'] < 449
                                   else 'ACTIVO' if value['x1'] < 493 else 'ESPERA' if value['x1'] < 536 else 'RESERVA')
                            columns.setdefault(key, []).append(value)
                    reason = '' if len(item['prices']) == expected and item['description'] and (kind == 'maquinaria' or item['unit']) and (not columns or all(len(columns.get(k, [])) == 1 for k in ['VA_USD','VA_MXN',*variants])) else 'COLUMNAS_INCOMPLETAS_O_AMBIGUAS'
                    for column, variant in enumerate(variants):
                        if kind == 'maquinaria':
                            values = columns.get(variant, [])
                            original_price = values[0]['text'] if len(values) == 1 else ''
                        else:
                            original_price = item['prices'][0]['text'] if len(item['prices']) == 1 else ''
                        cost = str(Decimal(original_price[1:].replace(',', ''))) if original_price else ''
                        code = item['code'] + (f':{variant}' if kind == 'maquinaria' else '')
                        eid = f'{sid}:{number}:{ordinal}:{code}'
                        applicability = {'tipo_fuente': kind, 'modo_maquinaria': variant if kind == 'maquinaria' else None,
                            'sin_ajuste_inflacion': True, 'no_inventa_desglose_APU': True,
                            'acarreos': 'NO_INCLUIDOS; consultar alcance del concepto' if kind != 'maquinaria' else 'NO_APLICA'}
                        raw = {**item, 'columna_precio': variant, 'valor_bruto': original_price}
                        records['partida_catalogo'].append(row('partida_catalogo', partida_id=eid, fuente_id=sid,
                            codigo=code, codigo_fuente=item['code'], tipo_registro='COSTO_HORARIO' if kind == 'maquinaria' else 'PRECIO_UNITARIO',
                            descripcion=item['description'] + (f' — modo {variant}' if kind == 'maquinaria' else ''),
                            descripcion_bruta=item['description'], unidad='h' if kind == 'maquinaria' else item['unit'],
                            unidad_bruta='hora efectiva' if kind == 'maquinaria' else item['unit'], costo=cost, moneda='MXN',
                            naturaleza_costo='COSTO_DIRECTO_REFERENCIAL', fecha_precio=effective, pagina_inicio=number, pagina_fin=number,
                            confianza='1', estado_revision='CUARENTENA' if reason else REVISION,
                            aplicabilidad=json.dumps(applicability, ensure_ascii=False), registro_bruto=json.dumps(raw, ensure_ascii=False)))
                        if reason:
                            records['incidencia_extraccion'].append(row('incidencia_extraccion', incidencia_id=eid+':columns',
                                fuente_id=sid, pagina_pdf=number, entidad_tipo='PARTIDA', entidad_id=eid,
                                severidad='BLOQUEANTE', codigo=reason, mensaje='Verificar las columnas contra el PDF original', evidencia=json.dumps(raw), resuelta='false'))
            if kind == 'parametricos' and number == 28:
                words = page.extract_words()
                for a in words:
                    if not (a['x0'] < 65 and a['top'] > 130 and a['text'].isdigit()): continue
                    same = [w for w in words if abs(w['top'] - a['top']) < 3]
                    city = joined([w for w in same if 125 <= w['x0'] < 205])
                    values = sorted((w for w in same if w['x0'] > 285 and re.fullmatch(r'\d\.\d{4}', w['text'])), key=lambda w: w['x0'])
                    if not city or len(values) != 5: raise ValueError('Fila FIC incompleta; no se intercambian columnas')
                    scopes = ['GENERAL', 'CARRETERA_ASFALTICA', 'CARRETERA_HIDRAULICA', 'ESTRUCTURA_CONCRETO', 'ESTRUCTURA_METALICA']
                    for scope, value in zip(scopes, values, strict=True):
                        records['factor_geografico'].append(row('factor_geografico', factor_id=f'{sid}:FIC:{a["text"]}:{scope}',
                            fuente_id=sid, pagina_pdf=number, tipo_factor='FIC_INTERCIUDAD', valor=value['text'], valor_bruto=value['text'],
                            localidad_base=city, instrucciones=json.dumps({'fic_especialidad': scope, 'no_es_inflacion': True}),
                            confianza='1', estado_revision=REVISION))
            page.close()
        # Duplicated printed codes are retained, but cannot silently select a price.
        for item in records['partida_catalogo']:
            if seen[item['codigo_fuente']] > 1:
                item['estado_revision'] = 'CUARENTENA'
        for item in records['modelo_parametrico']:
            if seen[item['codigo']] > 1: item['estado_revision'] = 'CUARENTENA'
        if not records['partida_catalogo'] and not records['modelo_parametrico']: raise ValueError('Ninguna tabla de precios identificada en la fuente')
    return records


def write_package(destination: Path, records):
    if destination.exists(): raise ValueError('El destino ya existe; conserve la edición previa')
    destination.mkdir(parents=True)
    (destination / 'data').mkdir()
    files = {}
    for table, columns in SCHEMA.items():
        path = destination / 'data' / f'{table}.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader(); writer.writerows(records[table])
        files[f'data/{table}.csv'] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    manifest = {'format': 'MEGALODON_CATALOGOS_POSTGRES_2026', 'version': 1, 'files': files,
                'counts': {t: len(records[t]) for t in SCHEMA}}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
