"""Paquetes adversos no pueden convertir evidencia pendiente en precios."""
import csv
import hashlib
import json

import pytest

from app.services.catalogo_package import (
    CatalogPackageError, SCHEMA, digest, verify_package,
)


def write_package(root, rows):
    (root / 'data').mkdir(parents=True, exist_ok=True)
    files = {}
    for table, columns in SCHEMA.items():
        path = root / 'data' / f'{table}.csv'
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows.get(table, []))
        files[f'data/{table}.csv'] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    manifest = {'format': 'MEGALODON_CATALOGOS_POSTGRES_2026', 'version': 1,
                'files': files, 'counts': {t: len(rows.get(t, [])) for t in SCHEMA}}
    (root / 'manifest.json').write_text(json.dumps(manifest))


def test_browser_fixture_builds_and_verifies_in_a_missing_parent_directory(tmp_path):
    from tests.fixtures.catalog_import import make_synthetic_package
    package, originals, rows = make_synthetic_package(tmp_path / 'new' / 'nested')
    verified = verify_package(package, originals)
    assert verified.records['fuente'][0]['fuente_id'] == 'SYNTHETIC'
    assert verified.records['partida_catalogo'] == rows['partida_catalogo']


@pytest.fixture
def package(tmp_path):
    originals = tmp_path / 'originals'
    originals.mkdir()
    source = originals / 'prefijo-distinto.pdf'
    source.write_bytes(b'PDF fixture: identity is content, not filename')
    def row(table, **values):
        base = dict.fromkeys(SCHEMA[table], '')
        for field in ('metadatos', 'aplicabilidad', 'registro_bruto', 'evidencia'):
            if field in base: base[field] = '{}'
        base.update(values)
        return base
    rows = {
        'fuente': [row('fuente', fuente_id='f', paginas='1', sha256=digest(source))],
        'pagina_fuente': [row('pagina_fuente', fuente_id='f', pagina_pdf='1',
                            texto_bruto='texto', caracteres='5', advertencias='[]',
                            texto_sha256=hashlib.sha256(b'texto').hexdigest())],
        'partida_catalogo': [row('partida_catalogo', partida_id='p', fuente_id='f',
                               pagina_inicio='1', pagina_fin='1', unidad='m3', costo='12.50',
                               estado_revision='VALIDADO_ESTRUCTURAL')],
        'componente_partida': [row('componente_partida', componente_id='c', partida_id='p',
                                  orden='1', pagina_pdf='1', estado_revision='VALIDADO_ESTRUCTURAL')],
    }
    issue = row('incidencia_extraccion', incidencia_id='i', fuente_id='f', pagina_pdf='1',
                entidad_tipo='COMPONENTE_PARTIDA', entidad_id='c',
                severidad='BLOQUEANTE', resuelta='false')
    root = tmp_path / 'package'
    return root, originals, rows, issue


def verify(data):
    root, originals, rows, _ = data
    write_package(root, rows)
    return verify_package(root, originals)


def test_original_identity_and_unverified_source(package):
    result = verify(package)
    assert result.operable_item_ids() == {'p'}
    assert result.report()['visual_review_certified'] is False
    next(package[1].glob('*.pdf')).write_bytes(b'different original')
    assert verify_package(package[0], package[1]).operable_item_ids() == set()


def test_child_blocker_blocks_price(package):
    package[2]['incidencia_extraccion'] = [package[3]]
    assert verify(package).operable_item_ids() == set()


def test_unidentified_blocker_quarantines_entire_source(package):
    package[3]['entidad_id'] = 'unparsed-header'
    package[2]['incidencia_extraccion'] = [package[3]]
    result = verify(package)
    assert result.blocked_source_ids == {'f'}
    assert result.operable_item_ids() == set()


def test_child_pending_review_blocks_price_even_without_issue(package):
    package[2]['componente_partida'][0]['estado_revision'] = 'REQUIERE_REVISION'
    assert verify(package).operable_item_ids() == set()


@pytest.mark.parametrize('change', ['nan', 'orphan', 'unknown_state', 'boolean_string', 'empty_source'])
def test_invalid_records_rejected(package, change):
    item = package[2]['partida_catalogo'][0]
    if change == 'nan': item['costo'] = 'NaN'
    if change == 'orphan': package[2]['componente_partida'][0]['partida_id'] = 'absent'
    if change == 'unknown_state': item['estado_revision'] = 'APPROVED'
    if change == 'boolean_string': item['aplicabilidad'] = '{"no_usar_para_costear":"false"}'
    if change == 'empty_source': item['fuente_id'] = ''
    with pytest.raises(CatalogPackageError): verify(package)


def test_tampered_csv_rejected(package):
    verify(package)
    with (package[0] / 'data/partida_catalogo.csv').open('a') as stream:
        stream.write('extra\n')
    with pytest.raises(CatalogPackageError, match='alterado'):
        verify_package(package[0], package[1])


def test_manifest_path_escape_rejected(package):
    verify(package)
    path = package[0] / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['files']['../originals/prefijo-distinto.pdf'] = {}
    path.write_text(json.dumps(manifest))
    with pytest.raises(CatalogPackageError, match='fuera de paquete'):
        verify_package(package[0], package[1])
