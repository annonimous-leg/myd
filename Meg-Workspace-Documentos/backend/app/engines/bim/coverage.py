"""IFC lineage, actual display coverage and independent mesh-volume diagnostics.

None of these diagnostics approve a contract quantity or a unit of payment.
"""
from collections import Counter
import math


def jerarquia_ifc(modelo):
    entities = modelo.by_type('IfcElement')
    products = {e.GlobalId: e for e in entities}
    if None in products or len(products) != len(entities):
        raise ValueError('GlobalId IFC ausente o duplicado')
    parents = {gid: set() for gid in products}
    children = {gid: set() for gid in products}
    relations = {gid: [] for gid in products}
    for gid, entity in products.items():
        for relation in (*getattr(entity, 'Decomposes', ()), *getattr(entity, 'Nests', ())):
            parent = relation.RelatingObject.GlobalId
            if parent in products:
                parents[gid].add(parent)
                children[parent].add(gid)
                relations[gid].append({"global_id": relation.GlobalId, "tipo": relation.is_a(), "padre_global_id": parent})

    def closure(gid, graph, path=frozenset()):
        if gid in path:
            raise ValueError('Jerarquía IFC cíclica')
        result = set(graph[gid])
        for adjacent in graph[gid]:
            result.update(closure(adjacent, graph, path | {gid}))
        return result

    return {gid: {
        'padres': sorted(parents[gid]), 'componentes': sorted(children[gid]),
        'relaciones_padre': sorted(relations[gid], key=lambda r: r['global_id']),
        'ancestros': sorted(closure(gid, parents)),
        'descendientes': sorted(closure(gid, children)),
    } for gid in products}


def inventario_cobertura(modelo, extraidos):
    selected = {e.global_id: e for e in extraidos}
    hierarchy = jerarquia_ifc(modelo)
    covered_by = {}
    for element in extraidos:
        if element.malla is None or not element.malla.vertices or not element.malla.caras:
            continue
        for component in element.propiedades.get('_componentes_geometria', []):
            covered_by.setdefault(component, []).append(element.global_id)
    rows = []
    for entity in sorted(modelo.by_type('IfcBuildingElement'), key=lambda e: e.id()):
        gid = entity.GlobalId
        lineage = hierarchy[gid]
        representation = getattr(entity, 'Representation', None) is not None
        if gid in selected:
            state = 'ADMITIDO'
        elif covered_by.get(gid):
            state = 'CUBIERTO_POR_CONJUNTO'
        elif representation:
            state = 'REPRESENTACION_PROPIA_PENDIENTE'
        elif lineage['componentes']:
            state = 'CONJUNTO_PENDIENTE'
        else:
            state = 'SIN_REPRESENTACION'
        rows.append({
            'global_id': gid, 'express_id': entity.id(), 'tipo': entity.is_a(),
            'nombre': entity.Name, 'admitido': gid in selected,
            'representacion_propia': representation, 'estado_cobertura': state,
            'cubierto_por': sorted(covered_by.get(gid, [])),
            'ancestros_admitidos': sorted(set(lineage['ancestros']) & selected.keys()),
            **lineage,
            'tratamiento_adicional': (
                'CONSERVAR_PROCEDENCIA_SIN_SUMAR_OTRA_CANTIDAD' if state == 'CUBIERTO_POR_CONJUNTO'
                else 'CLASIFICAR_FUNCION_Y_MATERIAL_ANTES_DE_MAPEAR' if entity.is_a('IfcBuildingElementProxy')
                else 'RECUPERAR_COMPONENTES_Y_REVISAR_ALCANCE_INTEGRAL_O_DESGLOSE' if state == 'CONJUNTO_PENDIENTE'
                else 'ADMITIR_TIPO_Y_VERIFICAR_UNIDAD_MEDICION_Y_ALCANCE' if state == 'REPRESENTACION_PROPIA_PENDIENTE'
                else 'MANTENER_REVISION_DE_MEDICION_Y_ALCANCE'
            ),
            'regla_candidata': (
                'PADRE_SI_CONCEPTO_INTEGRAL_O_COMPONENTES_SI_DESGLOSADO' if lineage['componentes']
                else 'COMPONENTE_SOLO_SI_CONCEPTO_SEPARADO' if lineage['padres']
                else 'MEDICION_SEGUN_UNIDAD_Y_ALCANCE_CONTRATADO'
            ),
            'fuente_regla': 'RELACIONES_IFC; HIPOTESIS_POR_CONFIRMAR_CON_CONTRATO',
            'partida_contractual': None,
            'sustento_contractual': None,
            'posible_doble_conteo': bool(lineage['padres'] or lineage['componentes']),
            'aprobacion_economica': 'PENDIENTE_DE_PARTIDA_Y_ALCANCE',
        })
    return rows


def conflictos_de_conjuntos(elementos):
    """Return ambiguous parent/component payment pairs within this model snapshot."""
    ids = {e.global_id for e in elementos}
    pairs = set()
    for element in elementos:
        properties = element.propiedades or {}
        for ancestor in properties.get('_jerarquia_ifc', {}).get('ancestros', []):
            if ancestor in ids:
                pairs.add((ancestor, element.global_id))
        for child in properties.get('_componentes_geometria', []):
            if child in ids:
                pairs.add((element.global_id, child))
    return [{'padre_global_id': a, 'componente_global_id': b} for a, b in sorted(pairs)]


def auditar_volumen(vertices, caras, declarado):
    """Closed oriented triangles + translated signed tetrahedra, independent of IFC APIs.

    Checks indexed topology and arithmetic only. Does not detect all self intersections,
    overlapping solids or establish net/gross/material/contract semantics.
    """
    result = {'estado': 'REQUIERE_REVISION', 'motivos': [], 'aprobado_economicamente': False}
    if not vertices or not caras or len(vertices) % 3 or len(caras) % 3:
        return {**result, 'motivos': ['MALLA_INCOMPLETA']}
    if not all(math.isfinite(v) for v in vertices):
        return {**result, 'motivos': ['COORDENADAS_NO_FINITAS']}
    points = list(zip(vertices[::3], vertices[1::3], vertices[2::3]))
    if any(not isinstance(i, int) or not 0 <= i < len(points) for i in caras):
        return {**result, 'motivos': ['INDICES_INVALIDOS']}
    edges, direction = Counter(), Counter()
    volumes = []
    origin = points[0]
    for i in range(0, len(caras), 3):
        a, b, c = caras[i:i + 3]
        for x, y in ((a, b), (b, c), (c, a)):
            key = (min(x, y), max(x, y))
            edges[key] += 1
            direction[key] += 1 if x < y else -1
        p, q, r = (tuple(v - o for v, o in zip(points[k], origin)) for k in (a, b, c))
        cross = (q[1]*r[2] - q[2]*r[1], q[2]*r[0] - q[0]*r[2], q[0]*r[1] - q[1]*r[0])
        volumes.append(math.fsum(p[k] * cross[k] for k in range(3)) / 6)
        ab = tuple(q[k] - p[k] for k in range(3))
        ac = tuple(r[k] - p[k] for k in range(3))
        area_cross = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
        if a == b or b == c or c == a or math.hypot(*area_cross) <= 1e-16:
            result['motivos'].append('TRIANGULOS_DEGENERADOS')
    independent = abs(math.fsum(volumes))
    result.update(volumen_independiente_m3=independent,
                  aristas_abiertas=sum(n == 1 for n in edges.values()),
                  aristas_no_manifold=sum(n > 2 for n in edges.values()))
    if any(n != 2 for n in edges.values()):
        result['motivos'].append('MALLA_NO_CERRADA_O_NO_MANIFOLD')
    if any(value for value in direction.values()):
        result['motivos'].append('ORIENTACION_INCONSISTENTE')
    if not math.isfinite(independent) or independent <= 0:
        result['motivos'].append('VOLUMEN_NO_POSITIVO')
    if declarado is None or not math.isfinite(float(declarado)) or not math.isclose(
        independent, float(declarado), rel_tol=1e-6, abs_tol=1e-8,
    ):
        result['motivos'].append('VOLUMEN_NO_COINCIDE')
    result['motivos'] = sorted(set(result['motivos']))
    if not result['motivos']:
        result['estado'] = 'CONSISTENCIA_NUMERICA_VERIFICADA'
    return result
