"""Verificación cerrada de paquetes fuente: nunca ejecuta SQL recibido.

La validación estructural conserva incidencias y no certifica revisión visual.
Las fuentes se resuelven por SHA-256, sin depender de prefijos del nombre.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCHEMA = json.loads((Path(__file__).parents[1] / 'data/catalogos/package_schema_v1.json').read_text())
KEYS = {name: columns[0] for name, columns in SCHEMA.items()}
REVISION = {'VALIDADO_ESTRUCTURAL', 'REQUIERE_REVISION', 'CUARENTENA', 'INFORMATIVO'}
JSON_FIELDS = {'metadatos', 'advertencias', 'efecto_normalizado', 'aplicabilidad', 'registro_bruto', 'evidencia'}
NUMERIC_FIELDS = {'valor', 'costo', 'confianza', 'cantidad', 'costo_unitario', 'importe', 'medida_base',
                  'costo_por_unidad', 'costo_total', 'rango_inferior', 'rango_superior', 'porcentaje', 'precio'}
PARENT = {'componente_partida': ('partida_catalogo', 'partida_id'),
          'componente_modelo': ('modelo_parametrico', 'modelo_id'),
          'desglose_modelo': ('modelo_parametrico', 'modelo_id')}
ENTITY_TABLE = {'PARTIDA': 'partida_catalogo', 'COMPONENTE_PARTIDA': 'componente_partida',
                'MODELO': 'modelo_parametrico', 'COMPONENTE_MODELO': 'componente_modelo',
                'FACTOR_GEOGRAFICO': 'factor_geografico', 'PRECIO_REGIONAL': 'precio_regional'}


class CatalogPackageError(ValueError):
    """El paquete no cumple su contrato; no debe importarse parcialmente."""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def strict_json(value: str):
    def reject(value):
        raise CatalogPackageError(f'Constante JSON no finita: {value}')
    return json.loads(value, parse_constant=reject)


@dataclass
class VerifiedPackage:
    package_sha256: str
    records: dict[str, list[dict[str, str]]]
    verified_source_ids: frozenset[str]
    missing_source_ids: frozenset[str]
    blocked: frozenset[tuple[str, str]]
    blocked_source_ids: frozenset[str]

    def operable_item_ids(self) -> frozenset[str]:
        result = set()
        for row in self.records['partida_catalogo']:
            key = ('partida_catalogo', row['partida_id'])
            unit = row['unidad'].strip().lower()
            forbidden = strict_json(row['aplicabilidad']).get('no_usar_para_costear', False)
            if (row['fuente_id'] in self.verified_source_ids
                    and row['fuente_id'] not in self.blocked_source_ids and key not in self.blocked
                    and row['estado_revision'] == 'VALIDADO_ESTRUCTURAL'
                    and unit and unit not in {'%', 'iva'} and not forbidden
                    and row['costo'] and Decimal(row['costo']) > 0):
                result.add(row['partida_id'])
        return frozenset(result)

    def report(self) -> dict:
        sources = self.records['fuente']
        return {'package_sha256': self.package_sha256,
                'counts': {k: len(v) for k, v in self.records.items()},
                'sources_verified': len(self.verified_source_ids),
                'sources_missing': len(self.missing_source_ids),
                'sources_quarantined': len(self.blocked_source_ids),
                'pages_verified': sum(int(s['paginas']) for s in sources if s['fuente_id'] in self.verified_source_ids),
                'unresolved_blockers': sum(i['severidad'] == 'BLOQUEANTE' and i['resuelta'] == 'false'
                                          for i in self.records['incidencia_extraccion']),
                'blocked_entities': dict(Counter(table for table, _ in self.blocked)),
                'operable_items_structural_only': len(self.operable_item_ids()),
                'visual_review_certified': False}


def verify_package(package: Path, originals: Path) -> VerifiedPackage:
    package = package.resolve()
    manifest = strict_json((package / 'manifest.json').read_text())
    if manifest.get('format') != 'MEGALODON_CATALOGOS_POSTGRES_2026' or manifest.get('version') != 1:
        raise CatalogPackageError('Formato o versión de paquete no soportado')
    fingerprints = {}
    for relative, expected in manifest['files'].items():
        path = (package / relative).resolve()
        if not path.is_relative_to(package) or not path.is_file():
            raise CatalogPackageError(f'Archivo fuera de paquete o ausente: {relative}')
        actual = digest(path)
        if actual != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise CatalogPackageError(f'Archivo alterado: {relative}')
        fingerprints[relative] = actual
    records = {}
    for table, columns in SCHEMA.items():
        relative = f'data/{table}.csv'
        if relative not in fingerprints:
            raise CatalogPackageError(f'CSV sin firma en manifiesto: {table}')
        with (package / relative).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != columns:
                raise CatalogPackageError(f'Contrato de columnas incorrecto: {table}')
            rows = list(reader)
        if len(rows) != manifest['counts'].get(table):
            raise CatalogPackageError(f'Conteo incorrecto: {table}')
        seen = set()
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise CatalogPackageError(f'Fila CSV incompleta o con columnas extra: {table}')
            key = (row['fuente_id'], row['pagina_pdf']) if table == 'pagina_fuente' else row[KEYS[table]]
            if not key or key in seen:
                raise CatalogPackageError(f'Identidad vacía o duplicada: {table}/{key}')
            seen.add(key)
            for field, value in row.items():
                if field in JSON_FIELDS:
                    decoded = strict_json(value)
                    if field == 'aplicabilidad' and not isinstance(decoded, dict):
                        raise CatalogPackageError('Aplicabilidad debe ser un objeto JSON')
                    if (field == 'aplicabilidad' and 'no_usar_para_costear' in decoded
                            and not isinstance(decoded['no_usar_para_costear'], bool)):
                        raise CatalogPackageError('no_usar_para_costear debe ser booleano')
                if field in NUMERIC_FIELDS and value:
                    try:
                        number = Decimal(value)
                        if not number.is_finite(): raise InvalidOperation
                    except InvalidOperation as exc:
                        raise CatalogPackageError(f'Número no finito/inválido: {table}/{field}') from exc
                    if field == 'confianza' and not 0 <= number <= 1:
                        raise CatalogPackageError(f'Confianza fuera de rango: {table}')
            if 'estado_revision' in row and row['estado_revision'] not in REVISION:
                raise CatalogPackageError(f'Estado de revisión desconocido: {table}')
            if table == 'incidencia_extraccion' and (row['resuelta'] not in {'true', 'false'}
                    or row['severidad'] not in {'INFO', 'ADVERTENCIA', 'BLOQUEANTE'}):
                raise CatalogPackageError('Estado de incidencia inválido')
        records[table] = rows
    index = {name: {row[KEYS[name]]: row for row in rows} for name, rows in records.items() if name != 'pagina_fuente'}
    sources = index['fuente']
    pages = {(r['fuente_id'], int(r['pagina_pdf'])): r for r in records['pagina_fuente']}
    for sid, source in sources.items():
        n = int(source['paginas'])
        if n <= 0 or {p for s, p in pages if s == sid} != set(range(1, n + 1)):
            raise CatalogPackageError(f'Cobertura de páginas incompleta: {sid}')
    natural = set()
    for table, rows in records.items():
        for row in rows:
            sid = row.get('fuente_id')
            if table in PARENT:
                parent_table, foreign_key = PARENT[table]
                parent = index[parent_table].get(row[foreign_key])
                if parent is None: raise CatalogPackageError(f'Padre ausente: {table}')
                sid = parent['fuente_id']
                pair = (table, row[foreign_key], row['orden'])
                if pair in natural: raise CatalogPackageError(f'Orden duplicado: {table}')
                natural.add(pair)
                if int(row['orden']) <= 0: raise CatalogPackageError(f'Orden inválido: {table}')
            if table != 'ubicacion' and (not sid or sid not in sources):
                raise CatalogPackageError(f'Fuente ausente: {table}')
            for field in ('pagina_pdf', 'pagina_inicio', 'pagina_fin'):
                if row.get(field) and sid and (sid, int(row[field])) not in pages:
                    raise CatalogPackageError(f'Página fuera de fuente: {table}')
            if row.get('pagina_inicio') and row.get('pagina_fin') and int(row['pagina_fin']) < int(row['pagina_inicio']):
                raise CatalogPackageError(f'Rango de páginas invertido: {table}')
            if row.get('ubicacion_id') and row['ubicacion_id'] not in index['ubicacion']:
                raise CatalogPackageError(f'Ubicación ausente: {table}')
            if table == 'pagina_fuente':
                raw = row['texto_bruto'].encode()
                if hashlib.sha256(raw).hexdigest() != row['texto_sha256'] or len(row['texto_bruto']) != int(row['caracteres']):
                    raise CatalogPackageError('Texto de página alterado')
    verified, missing = set(), set()
    original_hashes = {digest(path) for path in originals.rglob('*.pdf')}
    for sid, source in sources.items():
        (verified if source['sha256'] in original_hashes else missing).add(sid)
    blocked, blocked_sources = set(), set()
    for table, (parent_table, foreign_key) in PARENT.items():
        for row in records[table]:
            if row['estado_revision'] != 'VALIDADO_ESTRUCTURAL':
                blocked.add((table, row[KEYS[table]]))
                blocked.add((parent_table, row[foreign_key]))
    for issue in records['incidencia_extraccion']:
        if issue['severidad'] != 'BLOQUEANTE' or issue['resuelta'] != 'false': continue
        table = ENTITY_TABLE.get(issue['entidad_tipo'])
        if table is None:
            raise CatalogPackageError('Tipo de entidad bloqueante desconocido')
        entity = index[table].get(issue['entidad_id'])
        if entity is None:
            # La extracción pudo fallar antes de generar una identidad. Se
            # conserva la evidencia y se impide operar con toda esa fuente.
            blocked_sources.add(issue['fuente_id'])
            continue
        source_id = entity.get('fuente_id')
        if table in PARENT:
            parent_table, foreign_key = PARENT[table]
            source_id = index[parent_table][entity[foreign_key]]['fuente_id']
        if source_id != issue['fuente_id']:
            raise CatalogPackageError('Incidencia asociada a una fuente diferente')
        blocked.add((table, issue['entidad_id']))
        if table in PARENT:
            parent_table, foreign_key = PARENT[table]
            blocked.add((parent_table, index[table][issue['entidad_id']][foreign_key]))
    identity = hashlib.sha256(json.dumps(fingerprints, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return VerifiedPackage(identity, records, frozenset(verified), frozenset(missing),
                           frozenset(blocked), frozenset(blocked_sources))
