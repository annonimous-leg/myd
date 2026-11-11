from pathlib import Path
from types import SimpleNamespace

import ifcopenshell
import pytest

from app.engines.bim.coverage import auditar_volumen, inventario_cobertura, jerarquia_ifc


VERTICES = [0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 4]
FACES = [0, 2, 1, 0, 1, 3, 0, 3, 2, 1, 2, 3]


def test_translated_closed_tetrahedron_matches_analytical_volume_without_approving_payment():
    mesh = [v + 1000000 for v in VERTICES]
    result = auditar_volumen(mesh, FACES, 4)
    assert result['estado'] == 'CONSISTENCIA_NUMERICA_VERIFICADA'
    assert result['volumen_independiente_m3'] == pytest.approx(4)
    assert result['aprobado_economicamente'] is False


def test_open_or_reversed_faces_cannot_pass_volume_review():
    opened = auditar_volumen(VERTICES, FACES[:-3], 4)
    assert 'MALLA_NO_CERRADA_O_NO_MANIFOLD' in opened['motivos']
    reversed_face = auditar_volumen(VERTICES, [0, 1, 2] + FACES[3:], 4)
    assert 'ORIENTACION_INCONSISTENTE' in reversed_face['motivos']
    wrong_volume = auditar_volumen(VERTICES, FACES, 8)
    assert 'VOLUMEN_NO_COINCIDE' in wrong_volume['motivos']


def test_lineage_is_not_display_coverage_until_child_mesh_is_actually_used():
    source = ifcopenshell.open(str(Path(__file__).parents[1] / 'fixtures/ifc/wall_millimetres.ifc'))
    wall = source.by_type('IfcWall')[0]
    parent = source.create_entity('IfcRoof', GlobalId=ifcopenshell.guid.new())
    source.create_entity('IfcRelAggregates', GlobalId=ifcopenshell.guid.new(),
                         RelatingObject=parent, RelatedObjects=[wall])
    extracted = SimpleNamespace(global_id=parent.GlobalId, propiedades={},
                                malla=SimpleNamespace(vertices=VERTICES, caras=FACES))
    rows = {r['global_id']: r for r in inventario_cobertura(source, [extracted])}
    assert rows[wall.GlobalId]['ancestros_admitidos'] == [parent.GlobalId]
    assert rows[wall.GlobalId]['estado_cobertura'] == 'REPRESENTACION_PROPIA_PENDIENTE'
    extracted.propiedades['_componentes_geometria'] = [wall.GlobalId]
    covered = {r['global_id']: r for r in inventario_cobertura(source, [extracted])}
    assert covered[wall.GlobalId]['estado_cobertura'] == 'CUBIERTO_POR_CONJUNTO'
    assert covered[wall.GlobalId]['partida_contractual'] is None
    assert covered[wall.GlobalId]['sustento_contractual'] is None
    assert covered[wall.GlobalId]['posible_doble_conteo'] is True

    source.create_entity('IfcRelAggregates', GlobalId=ifcopenshell.guid.new(),
                         RelatingObject=wall, RelatedObjects=[parent])
    with pytest.raises(ValueError, match='cíclica'):
        jerarquia_ifc(source)


@pytest.mark.parametrize('fixture, source_type', [
    ('wall_millimetres.ifc', 'GEOMETRIA_CALCULADA'), ('wall_millimetres_qto.ifc', 'QTO_IFC'),
])
def test_audit_command_preserves_source_and_does_not_approve_payment(tmp_path, fixture, source_type):
    import json
    from scripts.audit_bim_coverage import audit
    source = Path(__file__).parents[1] / 'fixtures/ifc' / fixture
    audit(source, tmp_path)
    summary = json.loads((tmp_path / 'resumen.json').read_text())
    assert summary['admitidos'] == summary['mallas_admitidas'] == 1
    assert summary['fuentes_volumen_admitidos'] == {source_type: 1}
    assert summary['cantidades_economicas_aprobadas'] == 0
    assert summary['catalogos_de_otras_obras_aplicados'] is False
    row = json.loads((tmp_path / 'inventario.json').read_text())[0]
    assert row['partida_contractual'] is None
    assert row['aprobacion_economica'] == 'PENDIENTE_DE_PARTIDA_Y_ALCANCE'
