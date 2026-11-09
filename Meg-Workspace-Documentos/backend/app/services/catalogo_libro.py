"""Immutable source catalogue. Prices are quoted, never inferred from totals."""
import csv
import hashlib
import io
import os
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from app.core.errors import ErrorCode, MegalodonException

SOURCE = Path(os.environ.get("CATALOGO_LIBRO_CSV",
    str(Path(__file__).resolve().parents[2] / "data/private/catalogo.csv")))


@lru_cache(maxsize=1)
def cargar_catalogo():
    try:
        raw = SOURCE.read_bytes()
    except OSError as exc:
        raise MegalodonException(ErrorCode.ARCHIVO_ERROR,
            "Catálogo no instalado: configurar CATALOGO_LIBRO_CSV en el servidor", 503) from exc
    digest = hashlib.sha256(raw).hexdigest()
    items = {}
    for line, row in enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))), 2):
        key = hashlib.sha256(f"{digest}:{line}".encode()).hexdigest()
        reason = None
        try:
            price = Decimal(row["costo_unitario"])
            if not price.is_finite() or price <= 0:
                reason = "Precio ausente o no positivo"
        except (InvalidOperation, KeyError):
            price = None
            reason = "Precio no válido"
        if row.get("necesita_revision", "").strip().lower() != "false":
            reason = "Revisión pendiente en el CSV"
        if not row.get("descripcion", "").strip() or not row.get("unidad", "").strip():
            reason = "Descripción o unidad ausente"
        if row.get("unidad", "").strip().lower() in {"%", "iva"}:
            reason = "Porcentaje: requiere base de cálculo explícita"
        items[key] = {
            "id": key, "descripcion": row["descripcion"], "unidad": row["unidad"],
            "precio_unitario": str(price) if price is not None and price.is_finite() else None,
            "modelo_id": row["modelo_id"], "pagina": row["pdf_pagina_global"],
            "supuesto": row["supuesto"], "utilizable": reason is None, "bloqueo": reason,
            "fuente": SOURCE.name, "sha256": digest, "fila_csv": line,
            "original": row,
        }
    return items


def buscar(q="", skip=0, limit=50):
    words = q.casefold().split()
    matches = [item for item in cargar_catalogo().values()
               if all(word in (item["descripcion"] + " " + item["modelo_id"]).casefold() for word in words)]
    return {"total": len(matches), "items": matches[skip:skip + limit]}


def resolver(item_id):
    item = cargar_catalogo().get(item_id)
    if item is None:
        raise MegalodonException(ErrorCode.NOT_FOUND, "Referencia de catálogo inexistente o desactualizada")
    if not item["utilizable"]:
        raise MegalodonException(ErrorCode.BAD_REQUEST, item["bloqueo"])
    return item
