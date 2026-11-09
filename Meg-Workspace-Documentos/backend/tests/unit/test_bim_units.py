from pathlib import Path

import pytest
import ifcopenshell
import ifcopenshell.api

from app.engines.bim.motor_bim import MotorBIM

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 'ifc'


@pytest.mark.parametrize('filename', ['wall_metres.ifc', 'wall_millimetres.ifc'])
def test_same_wall_geometry_in_different_project_units(filename):
    motor = MotorBIM()
    motor.cargar_ifc(str(FIXTURES / filename))
    element = motor.cuantificar(['IfcWall']).elementos[0]
    assert element.volumen == pytest.approx(2.4)
    assert element.area == pytest.approx(16)
    assert element.bbox == pytest.approx([0, 0, 0, 2, .4, 3])


def test_qto_uses_independent_area_volume_units_and_explicit_override(tmp_path):
    model = ifcopenshell.open(str(FIXTURES / 'wall_millimetres_qto.ifc'))
    # Project has mm length, m2 area, m3 volume. Override NetVolume to cm3.
    quantity = next(q for q in model.by_type('IfcQuantityVolume') if q.Name == 'NetVolume')
    quantity.Unit = ifcopenshell.api.run('unit.add_si_unit', model, unit_type='VOLUMEUNIT', prefix='CENTI')
    quantity.VolumeValue = 2400000.0
    path = tmp_path / 'mixed.ifc'
    model.write(str(path))
    motor = MotorBIM()
    motor.cargar_ifc(str(path))
    element = motor.cuantificar(['IfcWall']).elementos[0]
    assert element.volumen == pytest.approx(2.4)
    assert element.area == pytest.approx(6)
    assert element.longitud == pytest.approx(2)
    assert element.fuente_volumen == 'QTO_IFC'


def test_invalid_volume_unit_preserves_element_other_quantities_and_geometry(tmp_path):
    model = ifcopenshell.open(str(FIXTURES / 'wall_millimetres_qto.ifc'))
    quantity = model.by_type('IfcQuantityVolume')[0]
    quantity.Unit = ifcopenshell.api.run('unit.add_si_unit', model, unit_type='AREAUNIT')
    path = tmp_path / 'invalid-unit.ifc'
    model.write(str(path))
    motor = MotorBIM(); motor.cargar_ifc(str(path))
    result = motor.cuantificar(['IfcWall'])
    assert not result.errores
    assert len(result.elementos) == 1
    elem = result.elementos[0]
    assert elem.volumen == pytest.approx(2.4)
    assert elem.fuente_volumen == 'GEOMETRIA_CALCULADA'
    assert elem.area == pytest.approx(6)
    assert elem.longitud == pytest.approx(2)
    assert elem.propiedades['_errores_qto']
