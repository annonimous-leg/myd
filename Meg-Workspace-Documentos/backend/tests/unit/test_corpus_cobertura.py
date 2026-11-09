import hashlib
import json

from app.engines.juridico.motor_busqueda_legal import MotorBusquedaLegal


def test_cobertura_usa_articulos_reales_y_expone_huecos(tmp_path):
    source = tmp_path / 'corpus.json'
    source.write_text(json.dumps({
        'LAASSP': {'total_articulos': 120, 'articulos': {
            '1': {'texto': 'Artículo 1. Texto de prueba'},
            '3': {'texto': 'Artículo 3. Texto de prueba'}}},
        'Manual Comité Adquisiciones': {'total_articulos': 0, 'articulos': {}}
    }))
    motor = MotorBusquedaLegal(source)
    coverage = motor.cobertura()
    assert coverage['total_articulos_consultables'] == 2
    assert coverage['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert coverage['vigencia_certificada'] is False
    law = coverage['documentos'][0]
    assert law['numeros_no_segmentados'] == [2]
    assert law['conteo_declarado_coincide'] is False
    assert coverage['documentos_sin_articulos'] == ['Manual Comité Adquisiciones']
    assert motor.listar_leyes()[0]['articulos'] == 2
    assert motor.obtener_articulo('laassp', '3')['contenido'] == 'Artículo 3. Texto de prueba'
