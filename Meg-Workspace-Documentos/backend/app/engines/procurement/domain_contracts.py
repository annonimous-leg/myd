# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""Contratos de dominio para snapshots entre módulos.

2026-08-30. Este archivo formaliza un patrón que Procurement ya usa de
manera implícita: cuando arma un TenderPackage, no copia BIM/CostOS/
Programación completos -- toma una FOTOGRAFÍA de lo que existía en el
momento (ver `_attach_quantification_sources`, `_materialize_budget`,
`_materialize_schedule` en materializer.py). El problema es que hoy esa
fotografía es un dict suelto sin forma común entre proveedores (BIM arma
un shape, Topografía arma otro). El contrato ahora conserva además una
revisión verificable de la fuente (`updated_at` + versión declarada cuando
existe), de modo que el gate puede detectar que el snapshot quedó obsoleto.

`DomainReference` identifica de dónde vino un dato -- qué recurso, de qué
tenant, qué tan seguros estamos de que no cambió.

`DomainSnapshot` envuelve el dato congelado junto con esa referencia y un
hash de lo que efectivamente se congeló, para que la pregunta "¿de dónde
salió esto?" tenga una respuesta verificable, no solo un `provider: "BIM"`
suelto en un dict.

APLICADO POR AHORA SOLO a technical.snapshots (BIM + Topografía) en
materializer.py, como plantilla -- no se retroaplicó a económico,
programación ni legal en esta ronda. Ver CAMBIOS para el razonamiento de
por qué un flujo primero, no los cinco a la vez.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class DomainReference:
    """Identifica un recurso de otro dominio sin copiar su contenido."""

    resource_type: str  # p.ej. "BIM_MODEL", "TOPOGRAFIA_VOLUMEN"
    resource_id: str
    tenant_id: str
    revision: str | None = None  # versión/edición del recurso, si el engine origen la expone
    content_hash: str | None = None  # hash del recurso completo en su fuente, si existe; None si el engine origen no lo calcula todavía

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "tenant_id": self.tenant_id,
            "revision": self.revision,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class DomainSnapshot:
    """Fotografía de dominio con payload recursivamente inmutable."""

    source: DomainReference
    snapshot: Any
    engine_version: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    output_hash: str = ""

    def __post_init__(self) -> None:
        frozen = _freeze_payload(self.snapshot)
        object.__setattr__(self, "snapshot", frozen)
        computed = _hash_payload(_thaw_payload(frozen))
        if self.output_hash and self.output_hash != computed:
            raise ValueError("output_hash no coincide con el payload congelado")
        object.__setattr__(self, "output_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        # Metadata temporal útil para auditoría humana; NO forma parte del
        # modelo canónico ni de su hash.
        return {**self.to_canonical_dict(), "captured_at": self.captured_at.isoformat()}

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "snapshot": _thaw_payload(self.snapshot),
            "engine_version": self.engine_version,
            "output_hash": self.output_hash,
        }


def _freeze_payload(value: Any) -> Any:
    """Convierte un payload JSON-like en una estructura recursivamente inmutable."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze_payload(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_payload(v) for v in value)
    if isinstance(value, set):
        raise TypeError("DomainSnapshot no admite sets; el payload debe ser JSON determinista.")
    return value


def _thaw_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw_payload(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw_payload(v) for v in value]
    return value


def _hash_payload(payload: dict[str, Any] | list[Any]) -> str:
    """sha256 del payload serializado de forma determinista (claves ordenadas).

    Esto es el hash de LO QUE SE CONGELÓ, no del recurso origen completo --
    permite verificar más tarde que un snapshot guardado no fue editado a
    mano, aunque no permite (todavía) verificar que siga coincidiendo con
    el estado actual de la fuente. Eso requeriría que cada engine origen
    exponga su propio content_hash -- ver DomainReference.content_hash,
    hoy None para BIM/Topografía porque ModeloBIM/CalculoVolumen no lo
    calculan.
    """
    normalized = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def source_revision_token(updated_at: datetime, declared_revision: str | None = None) -> str:
    """Construye una revisión verificable sin inventar un content hash.

    El timestamp `updated_at` pertenece a la fuente y cambia cuando la fila se
    modifica. Si el dominio además expone una versión declarada (por ejemplo,
    versión IFC), ambas forman una revisión compuesta. Esto permite detectar
    que un snapshot quedó obsoleto sin fingir que el engine origen calcula un
    hash de sus bytes.
    """
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    else:
        updated_at = updated_at.astimezone(timezone.utc)
    declared = "" if declared_revision is None else str(declared_revision)
    return f"declared:{declared}|updated_at:{updated_at.isoformat()}"


def snapshot_source_is_current(stored_revision: str | None, current_revision: str | None) -> bool:
    """Devuelve True sólo cuando ambas revisiones existen y coinciden exactamente."""
    return bool(stored_revision) and current_revision is not None and stored_revision == current_revision


def make_reference(
    resource_type: str, resource_id: UUID | str, tenant_id: UUID | str,
    revision: str | None = None, content_hash: str | None = None,
) -> DomainReference:
    return DomainReference(
        resource_type=resource_type, resource_id=str(resource_id), tenant_id=str(tenant_id),
        revision=revision, content_hash=content_hash,
    )
