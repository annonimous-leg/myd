
from dataclasses import dataclass

from app.engines.bim.heuristics import estimar_duracion_4d, resumir_grupo_bim4d, peso_geometrico_elemento


@dataclass
class DummyElemento:
    area: float | None = None
    volumen: float | None = None
    longitud: float | None = None


def test_peso_geometrico_prefiere_area_y_es_determinista():
    e1 = DummyElemento(area=12.5, volumen=99.0, longitud=1.0)
    e2 = DummyElemento(volumen=12.5)
    assert peso_geometrico_elemento(e1) == 12.5
    assert peso_geometrico_elemento(e2) == 12.5


def test_resumen_grupo_bim4d_calcula_promedios():
    resumen = resumir_grupo_bim4d([DummyElemento(area=2.0), DummyElemento(volumen=3.0), DummyElemento()])
    assert resumen.cantidad_elementos == 3
    assert resumen.peso_geometrico_total == 6.0
    assert resumen.peso_geometrico_promedio == 2.0


def test_estimacion_4d_escala_con_tamano_y_peso():
    grupo_ligero = [DummyElemento(area=1.0), DummyElemento(area=1.0)]
    grupo_pesado = [DummyElemento(area=10.0), DummyElemento(area=12.0), DummyElemento(area=8.0)]
    base = 5.0
    dur_ligero = estimar_duracion_4d(
        elementos=grupo_ligero,
        dias_base=base,
        promedio_cantidad_grupo=2.5,
        promedio_peso_grupo=4.0,
    )
    dur_pesado = estimar_duracion_4d(
        elementos=grupo_pesado,
        dias_base=base,
        promedio_cantidad_grupo=2.5,
        promedio_peso_grupo=4.0,
    )
    assert dur_pesado > dur_ligero
    assert dur_ligero >= 0.1


def test_estimacion_4d_no_regresa_un_fijo_constante():
    grupo = [DummyElemento()]
    dur = estimar_duracion_4d(
        elementos=grupo,
        dias_base=7.0,
        promedio_cantidad_grupo=1.0,
        promedio_peso_grupo=1.0,
    )
    assert dur == 7.0
