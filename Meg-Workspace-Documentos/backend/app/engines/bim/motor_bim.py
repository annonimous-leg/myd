# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor BIM/IFC para cuantificación real y extracción de malla renderizable.

Reescrito por completo: la versión anterior ya usaba ifcopenshell pero no
funcionaba en la práctica (ver bugs marcados abajo). Fuente de verdad para
volumen/área: primero el Quantity Set declarado en el IFC (Qto_*, tiene
significado de dominio que la geometría cruda no puede inferir, ej. el
"NetSideArea" de un muro es un solo lado, no la superficie total del
sólido); si el IFC no trae Qto, se calcula desde la geometría real como
respaldo, dejando marcado de dónde salió cada dato (`fuente_volumen`/
`fuente_area`) para que quien lo consuma (costeo) sepa qué tan confiable es.

También extrae la malla triangulada de cada elemento (vértices/caras ya en
metros y coordenadas de mundo) lista para mandarse tal cual a un
`THREE.BufferGeometry` en el frontend — el renderizado interactivo vive en
el navegador (WebGL/Three.js), este motor solo prepara los datos.
"""
from dataclasses import dataclass, field
import logging
import math
from typing import Dict, List, Optional, Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.util.unit

from app.core.errors import MegalodonException, ErrorCode

TIPOS_DEFAULT = [
    "IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcDoor", "IfcWindow",
    "IfcRoof", "IfcStair", "IfcFooting", "IfcCovering", "IfcRailing",
]

# Nombres de propiedad reales que usan los exportadores IFC más comunes
# (Revit, ArchiCAD, etc.) dentro de un Qto_*BaseQuantities.
# BUG ORIGINAL: solo se buscaba la llave exacta "Volume"/"Area"/"Length",
# que casi ningún exportador usa -> la extracción de cantidades nunca
# encontraba nada y todo salía en None.
CLAVES_VOLUMEN = ("NetVolume", "GrossVolume", "Volume")
CLAVES_AREA = ("NetSideArea", "NetArea", "GrossSideArea", "GrossArea", "NetFloorArea", "GrossFloorArea", "Area")
CLAVES_LONGITUD = ("Length", "NetLength")


logger = logging.getLogger(__name__)


@dataclass
class MallaElemento:
    """Malla triangulada lista para THREE.BufferGeometry en el frontend."""
    vertices: List[float]  # [x1,y1,z1, x2,y2,z2, ...] en metros, coords de mundo
    caras: List[int]       # [i1,i2,i3, ...] índices de triángulos


@dataclass
class ElementoBIMExtraido:
    global_id: str
    express_id: int
    tipo: str
    nombre: str
    volumen: Optional[float]
    area: Optional[float]
    longitud: Optional[float]
    fuente_volumen: str  # "QTO_IFC" | "GEOMETRIA_CALCULADA" | "NO_DISPONIBLE"
    fuente_area: str
    nivel: Optional[str] = None  # nombre del IfcBuildingStorey que lo contiene
    bbox: Optional[List[float]] = None  # [min_x,min_y,min_z, max_x,max_y,max_z] en metros
    propiedades: Dict[str, Any] = field(default_factory=dict)
    malla: Optional[MallaElemento] = None


@dataclass
class ResultadoCuantificacion:
    elementos: List[ElementoBIMExtraido]
    resumen_por_tipo: Dict[str, Dict[str, float]]
    niveles: List[str]  # nombres de IfcBuildingStorey detectados, en orden de elevación
    total_volumen: float
    total_area: float
    errores: List[str]


class MotorBIM:
    """Motor de procesamiento BIM/IFC."""

    def __init__(self):
        self.modelo: Optional[ifcopenshell.file] = None
        self._escala_longitud: float = 1.0
        self._settings = ifcopenshell.geom.settings()
        self._settings.set("use-world-coords", True)

    def cargar_ifc(self, ruta_archivo: str) -> ifcopenshell.file:
        """Carga un archivo IFC y detecta su factor de unidades."""
        try:
            self.modelo = ifcopenshell.open(ruta_archivo)
        except Exception as e:
            raise MegalodonException(ErrorCode.IFC_INVALIDO, f"Error al cargar IFC: {str(e)}")

        # Length scale applies to raw IFC elevations; geometry already uses SI.
        unit = ifcopenshell.util.unit.get_project_unit(self.modelo, "LENGTHUNIT")
        if unit is None:
            raise MegalodonException(ErrorCode.IFC_INVALIDO, "El IFC no declara su unidad de longitud")
        self._escala_longitud = ifcopenshell.util.unit.get_unit_scale(unit)
        if not math.isfinite(self._escala_longitud) or self._escala_longitud <= 0:
            raise MegalodonException(ErrorCode.IFC_INVALIDO, "Unidad de longitud IFC inválida")

        return self.modelo

    def cuantificar(
        self,
        tipos_elementos: Optional[List[str]] = None,
        extraer_malla: bool = True,
    ) -> ResultadoCuantificacion:
        """Cuantifica elementos del modelo IFC ya cargado."""
        if not self.modelo:
            raise MegalodonException(ErrorCode.BIM_ERROR, "No hay modelo IFC cargado")

        elementos: List[ElementoBIMExtraido] = []
        resumen: Dict[str, Dict[str, float]] = {}
        errores: List[str] = []
        total_volumen = 0.0
        total_area = 0.0

        tipos = tipos_elementos or TIPOS_DEFAULT
        escala = self._escala_longitud

        for tipo in tipos:
            for entidad in self.modelo.by_type(tipo):
                try:
                    elem = self._procesar_elemento(entidad, tipo, extraer_malla)
                    elementos.append(elem)

                    resumen.setdefault(tipo, {"cantidad": 0, "volumen_total": 0.0, "area_total": 0.0})
                    resumen[tipo]["cantidad"] += 1
                    resumen[tipo]["volumen_total"] += elem.volumen or 0.0
                    resumen[tipo]["area_total"] += elem.area or 0.0
                    total_volumen += elem.volumen or 0.0
                    total_area += elem.area or 0.0
                except Exception as e:
                    errores.append(f"Error en {tipo} id={entidad.id()}: {str(e)}")

        niveles = self._niveles_ordenados_por_elevacion(escala)

        return ResultadoCuantificacion(
            elementos=elementos,
            resumen_por_tipo=resumen,
            niveles=niveles,
            total_volumen=total_volumen,
            total_area=total_area,
            errores=errores,
        )

    def _niveles_ordenados_por_elevacion(self, escala: float) -> List[str]:
        """Nombres de IfcBuildingStorey ordenados de abajo hacia arriba
        (por Elevation), para que el selector de nivel en el frontend
        liste planta baja -> azotea en el orden correcto, no alfabético."""
        try:
            storeys = self.modelo.by_type("IfcBuildingStorey")
            con_elevacion = [
                (s.Name or f"Nivel {s.id()}", (s.Elevation or 0) * escala)
                for s in storeys
            ]
            con_elevacion.sort(key=lambda x: x[1])
            return [nombre for nombre, _ in con_elevacion]
        except Exception:
            return []

    def cotas_niveles(self) -> list[tuple[str, float]]:
        """Storey elevations in the same world coordinates and units as meshes."""
        levels = []
        for storey in self.modelo.by_type("IfcBuildingStorey"):
            placement = storey.ObjectPlacement
            if placement is None or not placement.is_a("IfcLocalPlacement"):
                continue
            z = float(ifcopenshell.util.placement.get_local_placement(placement)[2, 3])
            elevation = z * self._escala_longitud
            if math.isfinite(elevation):
                levels.append((storey.Name or f"Nivel {storey.id()}", elevation))
        return sorted(levels, key=lambda level: (level[1], level[0]))

    def _obtener_nivel(self, entidad) -> Optional[str]:
        """Nombre del IfcBuildingStorey que contiene al elemento, si existe."""
        try:
            contenedor = ifcopenshell.util.element.get_container(entidad)
            if contenedor is not None and contenedor.is_a("IfcBuildingStorey"):
                return contenedor.Name or f"Nivel {contenedor.id()}"
        except Exception as exc:
            logger.warning(
                "bim_container_read_failed",
                extra={"entity_id": entidad.id(), "entity_type": entidad.is_a(), "error": str(exc)},
            )
        return None

    @staticmethod
    def _cantidades_declaradas(entidad) -> dict:
        """Read whole-element quantities with occurrence values overriding their type."""
        tipo = ifcopenshell.util.element.get_type(entidad)
        definitions = list(getattr(tipo, "HasPropertySets", None) or ())
        for relation in getattr(entidad, "IsDefinedBy", ()) or ():
            if relation.is_a("IfcRelDefinesByProperties"):
                definition = relation.RelatingPropertyDefinition
                if definition.is_a("IfcPropertySetDefinitionSet"):
                    definitions.extend(definition.wrappedValue)
                else:
                    definitions.append(definition)

        qtos: dict = {}
        for definition in definitions:
            if definition.is_a("IfcElementQuantity"):
                quantities = qtos.setdefault(definition.Name, {})
                for quantity in definition.Quantities:
                    # A complex quantity can describe a material layer. Its
                    # children must not be read as totals for the entire element.
                    quantities[quantity.Name] = quantity
        return qtos

    def _cantidad_si(self, quantity, unit_type: str) -> float:
        unit = ifcopenshell.util.unit.get_property_unit(quantity, self.modelo)
        if unit is None or getattr(unit, "UnitType", None) != unit_type:
            raise ValueError(f"Cantidad {quantity.Name} sin unidad dimensional válida: {unit_type}")
        value = float(quantity[3]) * ifcopenshell.util.unit.get_unit_scale(unit)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Cantidad {quantity.Name} no finita o negativa")
        return value

    def _procesar_elemento(
        self, entidad, tipo: str, extraer_malla: bool
    ) -> ElementoBIMExtraido:
        propiedades: Dict[str, Any] = {}
        volumen_qto = area_qto = longitud_qto = None

        # 1) Propiedades y cantidades declaradas en el IFC.
        # BUG ORIGINAL: `import ifcopenshell` a secas no expone
        # `ifcopenshell.util.element` (los submódulos no se auto-importan
        # en Python), así que la llamada original tronaba con
        # AttributeError en cuanto se ejecutaba, no en el import.
        try:
            psets = ifcopenshell.util.element.get_psets(entidad)
            for pset_name, pset_data in psets.items():
                for prop_name, prop_value in pset_data.items():
                    propiedades[f"{pset_name}.{prop_name}"] = prop_value

            qtos = self._cantidades_declaradas(entidad)
            quantities = {}
            for field, keys, unit_type in (("volumen", CLAVES_VOLUMEN, "VOLUMEUNIT"),
                                          ("area", CLAVES_AREA, "AREAUNIT"),
                                          ("longitud", CLAVES_LONGITUD, "LENGTHUNIT")):
                for qto_data in qtos.values():
                    for key in keys:
                        quantity = qto_data.get(key)
                        if field in quantities or quantity is None or not quantity.is_a("IfcPhysicalSimpleQuantity"):
                            continue
                        try:
                            quantities[field] = self._cantidad_si(quantity, unit_type)
                        except (ValueError, TypeError, KeyError) as exc:
                            propiedades.setdefault("_errores_qto", []).append(str(exc))
                            logger.warning("bim_quantity_invalid", extra={"entity_id": entidad.id(), "error": str(exc)})
            volumen_qto, area_qto, longitud_qto = (quantities.get(k) for k in ("volumen", "area", "longitud"))
        except Exception as exc:
            logger.warning(
                "bim_psets_read_failed",
                extra={"entity_id": entidad.id(), "entity_type": entidad.is_a(), "error": str(exc)},
            )

        # 2) Geometría real: sirve de respaldo para volumen/área cuando el
        # IFC no trae Qto, y siempre sirve para mandar la malla al frontend.
        malla = None
        volumen_geom = area_geom = None
        bbox = None
        if getattr(entidad, "Representation", None) is not None:
            try:
                shape = ifcopenshell.geom.create_shape(self._settings, entidad)
                geometry = shape.geometry
                verts_crudos = geometry.verts
                caras = list(geometry.faces)
                # create_shape returns SI metres with convert-back-units=False.
                verts = list(verts_crudos)

                if extraer_malla:
                    malla = MallaElemento(vertices=verts, caras=caras)

                if verts:
                    xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
                    bbox = [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]

                try:
                    volumen_geom = ifcopenshell.util.shape.get_volume(geometry)
                except Exception as exc:
                    logger.warning(
                        "bim_volume_geom_failed",
                        extra={"entity_id": entidad.id(), "entity_type": entidad.is_a(), "error": str(exc)},
                    )
                try:
                    # OJO: esto es área de superficie TOTAL del sólido, no
                    # el área de una cara específica (ej. no equivale al
                    # "lado visible" de un muro). Se marca la fuente para
                    # que costeo sepa que es una aproximación geométrica.
                    area_geom = ifcopenshell.util.shape.get_area(geometry)
                except Exception as exc:
                    logger.warning(
                        "bim_area_geom_failed",
                        extra={"entity_id": entidad.id(), "entity_type": entidad.is_a(), "error": str(exc)},
                    )
            except Exception as e:
                propiedades["_error_geometria"] = str(e)

        nivel = self._obtener_nivel(entidad)

        # 3) El dato del IFC gana sobre el calculado: tiene significado de
        # dominio que la geometría cruda no puede inferir.
        if volumen_qto is not None:
            volumen, fuente_volumen = volumen_qto, "QTO_IFC"
        elif volumen_geom is not None:
            volumen, fuente_volumen = volumen_geom, "GEOMETRIA_CALCULADA"
        else:
            volumen, fuente_volumen = None, "NO_DISPONIBLE"

        if area_qto is not None:
            area, fuente_area = area_qto, "QTO_IFC"
        elif area_geom is not None:
            area, fuente_area = area_geom, "GEOMETRIA_CALCULADA"
        else:
            area, fuente_area = None, "NO_DISPONIBLE"

        # BUG ORIGINAL: getattr(entidad, "Name", "Sin nombre") no
        # funcionaba como default real -- el atributo Name SIEMPRE existe
        # en el esquema IFC (puede ser None), así que getattr regresaba
        # None en vez de "Sin nombre" para cualquier elemento sin nombre.
        nombre = entidad.Name if getattr(entidad, "Name", None) else "Sin nombre"

        return ElementoBIMExtraido(
            global_id=entidad.GlobalId,
            express_id=entidad.id(),
            tipo=tipo,
            nombre=nombre,
            volumen=volumen,
            area=area,
            longitud=longitud_qto,
            fuente_volumen=fuente_volumen,
            fuente_area=fuente_area,
            nivel=nivel,
            bbox=bbox,
            propiedades=propiedades,
            malla=malla,
        )
