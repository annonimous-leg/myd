"""Require a verified source and article reference for any active legal_rules row.

Hasta esta revisión, `legal_rules.source_id` y `legal_rules.article_id` eran
nullable sin restricción a nivel de base de datos. `ProcurementService.
create_legal_rule()` valida la referencia al crear una regla desde el
servicio, pero nada a nivel de esquema impedía que una fila terminara
`active = true` sin fundamento -- por un fixture de prueba, una migración de
datos, un UPDATE manual, o un futuro endpoint que no pase por ese servicio.

Esta revisión:

1. Desactiva (`active = false`) cualquier fila de `legal_rules` que hoy esté
   activa sin `source_id` o sin `article_id`, en vez de dejar que el propio
   ALTER TABLE truene a ciegas contra datos ya existentes. Las filas
   afectadas quedan explícitamente inactivas -- no se borran ni se
   reinterpretan.
2. Agrega dos CHECK constraints (mismo patrón que
   `ck_tender_rule_active_requires_tests` / `_hash` en la revisión
   `20260826_rule_execution_tenant_hardening`) que hacen estructuralmente
   imposible volver a insertar o activar una fila sin ambas referencias.

Lo que este constraint NO garantiza: que el artículo referenciado esté en
estado `VERIFICADO`/`ACTIVE` -- esa distinción vive en
`legal_articles.status` y hoy solo se aplica en la capa de servicio. Un
CHECK constraint de una sola tabla no puede validar el estado de una fila en
otra tabla sin un trigger. Si se necesita esa garantía a nivel de esquema,
el siguiente paso es un trigger, no este constraint.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260827_legal_rule_active_requires_fundamento"
down_revision = "20260826_rule_execution_tenant_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE legal_rules "
            "SET active = false "
            "WHERE active = true "
            "AND (source_id IS NULL OR article_id IS NULL)"
        )
    )

    op.create_check_constraint(
        "ck_legal_rules_active_requires_source",
        "legal_rules",
        "active = false OR source_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_legal_rules_active_requires_article",
        "legal_rules",
        "active = false OR article_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_legal_rules_active_requires_article", "legal_rules", type_="check")
    op.drop_constraint("ck_legal_rules_active_requires_source", "legal_rules", type_="check")
