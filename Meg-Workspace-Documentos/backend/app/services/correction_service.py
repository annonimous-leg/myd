# Copyright © 2026 Cristian Rodriguez
# Correction Service — workflow de aprobación de correcciones

from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from app.engines.licitacion.domain import (
    PropuestaCorreccion, Hallazgo, VersionProposicion, EstadoSolvencia
)


class CorrectionService:
    """Servicio de correcciones con workflow de aprobación.

    Flujo:
    1. Megalodon detecta error → propone corrección
    2. Usuario revisa → ACEPTA o RECHAZA
    3. Si ACEPTA → Megalodon aplica → recalcula → nueva versión
    4. Nunca sobrescribe versión anterior
    """

    def __init__(self):
        # En producción: repositorio DB. Aquí: memoria para estructura.
        self._versiones: Dict[str, List[VersionProposicion]] = {}
        self._correcciones: Dict[str, List[PropuestaCorreccion]] = {}

    async def proponer_correccion(self, proposicion_id: UUID, hallazgo: Hallazgo,
                                   cambio_propuesto: Dict[str, Any]) -> PropuestaCorreccion:
        """Crea propuesta de corrección."""
        propuesta = PropuestaCorreccion(
            hallazgo_id=hallazgo.id,
            descripcion_original=hallazgo.descripcion,
            descripcion_propuesta=f"Corrección propuesta: {cambio_propuesto.get('descripcion', 'Ver detalle')}",
            cambio=cambio_propuesto,
            estado="PENDIENTE"
        )

        key = str(proposicion_id)
        if key not in self._correcciones:
            self._correcciones[key] = []
        self._correcciones[key].append(propuesta)

        return propuesta

    async def decidir_correccion(self, proposicion_id: UUID, correccion_id: str,
                                  decision: str, usuario: str) -> PropuestaCorreccion:
        """Usuario decide sobre corrección: ACEPTADA o RECHAZADA."""
        key = str(proposicion_id)
        correcciones = self._correcciones.get(key, [])

        for c in correcciones:
            if c.id == correccion_id:
                c.estado = decision.upper()
                c.usuario_decision = usuario
                c.fecha_decision = datetime.utcnow()
                return c

        raise ValueError(f"Corrección {correccion_id} no encontrada")

    async def aplicar_correcciones_aceptadas(self, proposicion_id: UUID,
                                              documentos: Dict[str, Any]) -> Dict[str, Any]:
        """Aplica correcciones aceptadas y genera nueva versión."""
        key = str(proposicion_id)
        correcciones = self._correcciones.get(key, [])
        aceptadas = [c for c in correcciones if c.estado == "ACEPTADA"]

        documentos_corregidos = dict(documentos)

        for corr in aceptadas:
            cambio = corr.cambio
            if "documento" in cambio and "campo" in cambio and "valor" in cambio:
                doc_name = cambio["documento"]
                campo = cambio["campo"]
                valor = cambio["valor"]

                if doc_name in documentos_corregidos:
                    if isinstance(documentos_corregidos[doc_name], dict):
                        documentos_corregidos[doc_name][campo] = valor
                    else:
                        documentos_corregidos[doc_name] = {campo: valor}

        return documentos_corregidos

    async def crear_version(self, proposicion_id: UUID, version: int,
                            estado: EstadoSolvencia, hallazgos: List[Hallazgo],
                            correcciones: List[PropuestaCorreccion],
                            prefall: Any = None) -> VersionProposicion:
        """Crea nueva versión de proposición."""
        v = VersionProposicion(
            proposicion_id=proposicion_id,
            version=version,
            estado_validacion=estado,
            hallazgos=hallazgos,
            correcciones_aplicadas=correcciones,
            prefall_result=prefall
        )

        key = str(proposicion_id)
        if key not in self._versiones:
            self._versiones[key] = []
        self._versiones[key].append(v)

        return v

    async def listar_versiones(self, proposicion_id: UUID) -> List[VersionProposicion]:
        """Lista versiones de una proposición."""
        return self._versiones.get(str(proposicion_id), [])
