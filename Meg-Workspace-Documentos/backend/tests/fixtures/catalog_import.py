"""Synthetic source generator for disposable integration/browser acceptance."""
import hashlib
from app.services.catalogo_package import SCHEMA, digest
from tests.unit.test_catalogo_package import write_package


def make_synthetic_package(tmp_path):
    originals = tmp_path / 'originals'
    originals.mkdir(parents=True, exist_ok=True)
    pdf = originals / 'synthetic.pdf'
    from reportlab.pdfgen.canvas import Canvas
    canvas = Canvas(str(pdf)); canvas.drawString(40, 700, 'Synthetic catalogue fixture; no incluye IVA.'); canvas.save()
    def row(table, **kwargs):
        r = dict.fromkeys(SCHEMA[table], '')
        for field in ('metadatos', 'aplicabilidad', 'registro_bruto', 'evidencia', 'efecto_normalizado'):
            if field in r: r[field] = '{}'
        if 'estado_revision' in r: r['estado_revision'] = 'VALIDADO_ESTRUCTURAL'
        r.update(kwargs)
        return r
    text = 'Fixture sintética: no incluye IVA.'
    records = {
        'fuente': [row('fuente', fuente_id='SYNTHETIC', titulo='Synthetic test source', paginas='1', sha256=digest(pdf),
                       familia='TEST', moneda='MXN', fecha_vigencia='2026-01-01')],
        'pagina_fuente': [row('pagina_fuente', fuente_id='SYNTHETIC', pagina_pdf='1', texto_bruto=text,
                             texto_sha256=hashlib.sha256(text.encode()).hexdigest(), caracteres=str(len(text)), advertencias='[]')],
        'partida_catalogo': [row('partida_catalogo', partida_id='p', fuente_id='SYNTHETIC', codigo='TEST-EXC',
            tipo_registro='CONCEPTO_TRABAJO', unidad='m3', costo='152.43', moneda='MXN', fecha_precio='2026-01-01',
            descripcion='Synthetic excavation with six-decimal consumption', pagina_inicio='1', pagina_fin='1')],
        'componente_partida': [row('componente_partida', componente_id='c', partida_id='p', codigo='TEST-LABOR',
            tipo_componente='MANO DE OBRA', descripcion='Synthetic crew', unidad='jornada', cantidad='0.227273',
            costo_unitario='670.70', importe='152.43', orden='1', pagina_pdf='1')],
        'modelo_parametrico': [row('modelo_parametrico', modelo_id='m', fuente_id='SYNTHETIC', codigo='MODEL-TEST',
            nombre='Synthetic parametric model', unidad_medida_base='m2', medida_base='36', costo_por_unidad='4029.74',
            moneda='MXN', pagina_inicio='1', pagina_fin='1', aplicabilidad='{"no_es_APU_contractual":true}')],
        'factor_geografico': [row('factor_geografico', factor_id='f', fuente_id='SYNTHETIC', valor='0.897',
                                  localidad_base='Synthetic city', tipo_factor='FIC_INTERCIUDAD', pagina_pdf='1')],
    }
    package = tmp_path / 'package'
    write_package(package, records)
    return package, originals, records
