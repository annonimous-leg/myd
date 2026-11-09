"""Idempotencia de webhooks de pago -- F-07.

Hallazgo F-07 (auditoría externa 2026-09-01, verificado leyendo el
código): el webhook de Mercado Pago (app/api/v1/pagos.py ->
SuscripcionService.procesar_webhook) no comprobaba frescura de `ts` en la
firma (una notificación válida capturada una vez seguía siendo válida
para siempre) ni deduplicaba por evento -- cada entrega, incluido un
reenvío/replay, volvía a extender `fecha_fin` otros 31 días. Además
`suscripciones.external_id` se documentaba como "único por proveedor"
pero solo tenía index=True, sin restricción real.

Esta migración:
1. Crea `webhook_eventos_procesados` (proveedor, evento_id) con
   restricción única -- SuscripcionService.procesar_webhook inserta ahí
   ANTES de aplicar efectos; un evento_id repetido es rechazado por la
   base de datos, no por lógica de aplicación que se pueda saltear en
   una carrera.
2. Agrega la restricción única compuesta (proveedor, external_id) en
   `suscripciones`. Si ya existieran filas duplicadas en una base de
   datos existente, la migración FALLA (RuntimeError) en vez de
   continuar en silencio: no se borra dato de negocio real desde una
   migración de esquema (¿cuál fila es la "buena"?), pero tampoco se
   deja que Alembic marque esta revisión como aplicada sin haber
   logrado la restricción -- eso dejaría al código creyendo que existe
   una garantía de base de datos que en realidad no existe. Hay que
   resolver los duplicados a mano y volver a correr `alembic upgrade`.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260902_webhook_idempotency_suscripcion"
down_revision = "20260901_inconformidad_compliance_fields"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tablas = set(inspector.get_table_names())

    if "webhook_eventos_procesados" not in tablas:
        op.create_table(
            "webhook_eventos_procesados",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("proveedor", sa.String(length=20), nullable=False),
            sa.Column("evento_id", sa.String(length=255), nullable=False),
            sa.Column("procesado_en", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("proveedor", "evento_id", name="uq_webhook_evento_proveedor_id"),
        )

    constraints = {c["name"] for c in inspector.get_unique_constraints("suscripciones")}
    if "uq_suscripcion_proveedor_external_id" not in constraints:
        duplicados = bind.execute(sa.text(
            """
            SELECT proveedor, external_id, COUNT(*) AS n
            FROM suscripciones
            WHERE external_id IS NOT NULL
            GROUP BY proveedor, external_id
            HAVING COUNT(*) > 1
            """
        )).fetchall()
        if duplicados:
            # CORREGIDO (contra-auditoría V8, F-07 problema 2): la versión
            # anterior de esta migración solo imprimía un aviso y seguía --
            # upgrade() terminaba sin excepción, así que Alembic marcaba
            # esta revisión como aplicada AUNQUE la restricción no exista.
            # Cualquier código (incluida esta misma migración, si alguien
            # la corre de nuevo) quedaba creyendo que la invariante ya
            # está garantizada por la base de datos sin estarlo. Ahora se
            # falla duro: la revisión NO queda marcada como aplicada hasta
            # que los duplicados se resuelvan y `alembic upgrade` se
            # vuelva a correr.
            detalle = ", ".join(f"({p!r}, {e!r})×{n}" for p, e, n in duplicados[:10])
            raise RuntimeError(
                f"No se puede crear uq_suscripcion_proveedor_external_id: "
                f"{len(duplicados)} pares (proveedor, external_id) duplicados en "
                f"suscripciones (ej: {detalle}). Resolver los duplicados a mano "
                "(decidir cuál fila de cada par es la vigente) y volver a correr "
                "'alembic upgrade head'. La tabla webhook_eventos_procesados ya "
                "quedó creada en esta misma corrida -- no hace falta repetirla."
            )
        op.create_unique_constraint(
            "uq_suscripcion_proveedor_external_id", "suscripciones", ["proveedor", "external_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = {c["name"] for c in inspector.get_unique_constraints("suscripciones")}
    if "uq_suscripcion_proveedor_external_id" in constraints:
        op.drop_constraint("uq_suscripcion_proveedor_external_id", "suscripciones", type_="unique")

    tablas = set(inspector.get_table_names())
    if "webhook_eventos_procesados" in tablas:
        op.drop_table("webhook_eventos_procesados")
