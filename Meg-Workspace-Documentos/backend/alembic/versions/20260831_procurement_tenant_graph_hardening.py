"""Cierra integridad tenant en el grafo Procurement y jobs.

Convierte relaciones simples por UUID en FKs compuestas por (tenant_id, id),
previa comprobación de que no existan filas cruzadas. Esto evita que una fila
con un tenant pueda apuntar a un agregado de otro tenant aun cuando el servicio
omita accidentalmente un filtro.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260831_procurement_tenant_graph_hardening"
down_revision = "20260830_sancion_publicada_flag"
branch_labels = None
depends_on = None

_CHILD_RELATIONS = (
    ("tender_revisions", "tender_id", "tender_packages", "fk_tender_revision_tenant_tender", "CASCADE"),
    ("tender_requirements", "tender_id", "tender_packages", "fk_tender_requirement_tenant_tender", "CASCADE"),
    ("tender_evidence", "tender_id", "tender_packages", "fk_tender_evidence_tenant_tender", "CASCADE"),
    ("tender_evidence_links", "tender_id", "tender_packages", "fk_evidence_link_tenant_tender", "CASCADE"),
    ("tender_evidence_links", "evidence_id", "tender_evidence", "fk_evidence_link_tenant_evidence", "CASCADE"),
    ("tender_evidence_links", "requirement_id", "tender_requirements", "fk_evidence_link_tenant_requirement", "CASCADE"),
    ("tender_evidence_links", "artifact_id", "tender_artifacts", "fk_evidence_link_tenant_artifact", "CASCADE"),
    ("tender_artifacts", "tender_id", "tender_packages", "fk_tender_artifact_tenant_tender", "CASCADE"),
    ("tender_dependencies", "tender_id", "tender_packages", "fk_tender_dependency_tenant_tender", "CASCADE"),
    ("tender_approvals", "tender_id", "tender_packages", "fk_tender_approval_tenant_tender", "CASCADE"),
    ("submission_packages", "tender_id", "tender_packages", "fk_submission_package_tenant_tender", "CASCADE"),
    ("tender_preparation_runs", "tender_id", "tender_packages", "fk_preparation_run_tenant_tender", "CASCADE"),
    ("tender_preparation_stage_runs", "preparation_run_id", "tender_preparation_runs", "fk_stage_run_tenant_preparation", "CASCADE"),
    ("procurement_jobs", "tender_id", "tender_packages", "fk_procurement_job_tenant_tender", "CASCADE"),
    ("procurement_idempotency", "job_id", "procurement_jobs", "fk_procurement_idempotency_tenant_job", "CASCADE"),
    ("procurement_storage_intents", "job_id", "procurement_jobs", "fk_procurement_storage_intent_tenant_job", "RESTRICT"),
)


def _drop_single_fk(table: str, column: str) -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
         AND kcu.table_schema = tc.table_schema
        WHERE tc.table_schema = current_schema()
          AND tc.table_name = :table
          AND tc.constraint_type = 'FOREIGN KEY'
        GROUP BY tc.constraint_name
        HAVING count(*) = 1 AND min(kcu.column_name) = :column
        """
    ), {"table": table, "column": column}).first()
    if row:
        op.drop_constraint(row[0], table, type_="foreignkey")


def _assert_no_cross_tenant_mismatch(child: str, column: str, parent: str) -> None:
    bind = op.get_bind()
    sql = sa.text(
        f"SELECT 1 FROM {child} c JOIN {parent} p ON p.id = c.{column} "
        f"WHERE c.{column} IS NOT NULL AND c.tenant_id <> p.tenant_id LIMIT 1"
    )
    if bind.execute(sql).first() is not None:
        raise RuntimeError(f"No se puede endurecer {child}.{column}: existe relación cross-tenant.")


def _ensure_parent_unique(table: str, name: str) -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = (:table)::regclass
          AND conname = :name
        """
    ), {"table": table, "name": name}).first()
    if row is None:
        op.create_unique_constraint(name, table, ["tenant_id", "id"])


def upgrade() -> None:
    # Evidence links originally had tenant ownership but no tender_id.
    # Derive the aggregate from their evidence; never guess a default tenant.
    from sqlalchemy.dialects import postgresql
    op.add_column('tender_evidence_links', sa.Column('tender_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(sa.text('''
        UPDATE tender_evidence_links c SET tender_id = e.tender_id
        FROM tender_evidence e
        WHERE e.id = c.evidence_id AND e.tenant_id = c.tenant_id
    '''))
    unresolved = op.get_bind().execute(sa.text(
        'SELECT count(*) FROM tender_evidence_links WHERE tender_id IS NULL'
    )).scalar_one()
    if unresolved:
        raise RuntimeError('Evidence links have orphan or cross-tenant evidence; resolve before migration')
    op.alter_column('tender_evidence_links', 'tender_id', nullable=False)
    op.create_index('ix_tender_evidence_links_tender_id', 'tender_evidence_links', ['tender_id'])
    # All existing rows must be internally tenant-consistent before adding DB guards.
    for child, column, parent, _, _ in _CHILD_RELATIONS:
        _assert_no_cross_tenant_mismatch(child, column, parent)

    for table, name in (
        ("tender_packages", "uq_tender_packages_tenant_id"),
        ("tender_requirements", "uq_tender_requirements_tenant_id"),
        ("tender_evidence", "uq_tender_evidence_tenant_id"),
        ("tender_artifacts", "uq_tender_artifacts_tenant_id"),
        ("tender_preparation_runs", "uq_tender_preparation_runs_tenant_id"),
        ("procurement_jobs", "uq_procurement_jobs_tenant_id"),
    ):
        _ensure_parent_unique(table, name)

    for child, column, parent, name, _ in _CHILD_RELATIONS:
        _drop_single_fk(child, column)
        op.create_foreign_key(
            name,
            child,
            parent,
            ["tenant_id", column],
            ["tenant_id", "id"],
            ondelete=_,
        )


def downgrade() -> None:
    for child, _, _, name, _ in reversed(_CHILD_RELATIONS):
        op.drop_constraint(name, child, type_="foreignkey")

    # Restore the pre-hardening single-column FKs.
    for child, column, parent, _, ondelete in _CHILD_RELATIONS:
        op.create_foreign_key(
            f"fk_{child}_{column}_legacy", child, parent, [column], ["id"], ondelete=ondelete,
        )

    # Do not remove parent uniques created by 20260826_rule_execution_tenant_hardening.
    for table, name in reversed((
        ("procurement_jobs", "uq_procurement_jobs_tenant_id"),
        ("tender_preparation_runs", "uq_tender_preparation_runs_tenant_id"),
        ("tender_artifacts", "uq_tender_artifacts_tenant_id"),
    )):
        bind = op.get_bind()
        exists = bind.execute(sa.text(
            "SELECT 1 FROM pg_constraint WHERE conrelid = (:table)::regclass AND conname = :name"
        ), {"table": table, "name": name}).first()
        if exists:
            op.drop_constraint(name, table, type_="unique")
    op.drop_index('ix_tender_evidence_links_tender_id', table_name='tender_evidence_links')
    op.drop_column('tender_evidence_links', 'tender_id')
