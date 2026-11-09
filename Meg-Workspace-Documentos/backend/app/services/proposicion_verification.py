"""Review attestation with hashes of persisted evidence; never a SAT oracle.

The caller owns the transaction and locks the licitation and proposition first.
Document locks follow UUID order, matching co-signing's document boundary.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.expediente import Documento
from app.models.validador import ValidacionPropuesta
from app.services.firma_service import FirmaService
from app.services.licitacion_evaluation import conflict


def document_reference(document):
    signatures = (document.metadatos or {}).get("firmas", [])
    signature = signatures[-1] if signatures else None
    return {
        "id": str(document.id), "row_version": document.row_version,
        "sha256": signature["sha256_firmado"] if signature else document.hash_sha256,
        "storage_path": signature["storage_path_firmado"] if signature else document.storage_path,
    }


async def documents(db, lic, ids):
    rows = (await db.scalars(select(Documento).where(
        Documento.id.in_(ids), Documento.expediente_id == lic.expediente_id,
    ).order_by(Documento.id).with_for_update().execution_options(populate_existing=True))).all()
    if len(rows) != len(set(ids)):
        conflict("Todos los documentos de soporte deben pertenecer al expediente de la proposición.")
    return rows


async def attest(db, lic, prop, user, data):
    rows = await documents(db, lic, data.documentos_soporte)
    signer = FirmaService(db)
    for document in rows:
        signatures = (document.metadatos or {}).get("firmas", [])
        if signatures:
            await signer._signed_content(document, signatures[-1], user.tenant_id)
        else:
            await signer._contenido_real(document, user.tenant_id)
    flags = {"firma_valida": data.firma_valida, "integridad_valida": True,
             "cumplimiento_documental": data.cumplimiento_documental}
    verification_id = uuid4()
    snapshot = {
        "id": str(verification_id), "metodo": "ATESTACION_DOCUMENTAL",
        "autor_id": str(user.id), "fecha": datetime.now(timezone.utc).isoformat(),
        "dictamen": data.dictamen, "documentos": [document_reference(doc) for doc in rows],
        **flags,
    }
    db.add(ValidacionPropuesta(
        id=verification_id, tenant_id=user.tenant_id, expediente_id=lic.expediente_id,
        proposicion_id=prop.id, estado="REVISION_DOCUMENTAL",
        datos_entrada=snapshot,
        bitacora_evaluacion=[{
            "id_regla": flag, "seccion": "REVISION_DOCUMENTAL",
            "estatus": "PASA" if value else "FALLA", "valor_detectado": str(value),
            "valor_esperado": "True", "evidencia": data.dictamen,
        } for flag, value in flags.items()],
        creado_por_id=user.id, actualizado_por_id=user.id,
    ))
    for flag, value in flags.items():
        setattr(prop, flag, value)
    prop.verificacion_documental = snapshot
    prop.estado = "RECIBIDA" if all(flags.values()) else "DESECHADA"
    prop.motivo_desecho = None if all(flags.values()) else data.dictamen
    prop.actualizado_por_id = user.id


async def require_current(db, lic, prop):
    verification = prop.verificacion_documental or {}
    references = verification.get("documentos", [])
    try:
        ids = [UUID(ref["id"]) for ref in references]
    except (ValueError, TypeError, KeyError):
        conflict("La revisión documental contiene referencias inválidas.")
    if not ids:
        conflict("La proposición requiere revisión documental con evidencia persistida.")
    rows = await documents(db, lic, ids)
    current = {str(doc.id): document_reference(doc) for doc in rows}
    if any(current.get(ref["id"]) != ref for ref in references):
        conflict("Cambió un documento de soporte: se requiere una nueva revisión y evaluación.")
