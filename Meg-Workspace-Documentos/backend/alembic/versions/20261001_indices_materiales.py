"""Append-only levels and reviewed material mappings; preserve catalogue prices."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261001_indices_materiales"
down_revision = "20260930_identity_authority"
branch_labels = None
depends_on = None


def upgrade():
    op.execute('\nCREATE TABLE series_indices_costos (\n\tcodigo VARCHAR(120) NOT NULL, \n\tversion_metodologia VARCHAR(120) NOT NULL, \n\tnombre VARCHAR(300) NOT NULL, \n\tregion VARCHAR(120) NOT NULL, \n\tcondiciones_precio TEXT NOT NULL, \n\tperiodo_referencia VARCHAR(100) NOT NULL, \n\tevidencia JSONB NOT NULL, \n\tregistrado_por VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_serie_indice_version UNIQUE (codigo, version_metodologia)\n)\n\n')
    op.execute('\nCREATE TABLE observaciones_indices_costos (\n\tserie_id UUID NOT NULL, \n\tmes DATE NOT NULL, \n\tvalor NUMERIC(18, 8) NOT NULL, \n\tpublicado_el DATE NOT NULL, \n\tdocumento_sha256 VARCHAR(64) NOT NULL, \n\tevidencia JSONB NOT NULL, \n\tregistrado_por VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_observacion_indice_edicion UNIQUE (serie_id, mes, documento_sha256), \n\tCONSTRAINT ck_indice_nivel_positivo CHECK (valor > 0 AND valor < 10000000000), \n\tCONSTRAINT ck_indice_publicacion_posterior CHECK (publicado_el > mes), \n\tFOREIGN KEY(serie_id) REFERENCES series_indices_costos (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE INDEX ix_observaciones_indices_costos_serie_id ON observaciones_indices_costos (serie_id)')
    op.execute('\nCREATE TABLE vinculos_indices_insumos (\n\ttenant_id UUID NOT NULL, \n\tinsumo_id UUID NOT NULL, \n\tserie_id UUID NOT NULL, \n\tmes_base DATE NOT NULL, \n\tprecio_original NUMERIC(18, 4) NOT NULL, \n\tinsumo_original JSONB NOT NULL, \n\tfundamento TEXT NOT NULL, \n\tevidencia JSONB NOT NULL, \n\trevisado_por VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_vinculo_precio_positivo CHECK (precio_original > 0), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(insumo_id) REFERENCES insumos_catalogo (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(serie_id) REFERENCES series_indices_costos (id) ON DELETE RESTRICT\n)\n\n')
    op.execute('CREATE INDEX ix_vinculos_indices_insumos_insumo_id ON vinculos_indices_insumos (insumo_id)')
    op.execute('CREATE INDEX ix_vinculos_indices_insumos_serie_id ON vinculos_indices_insumos (serie_id)')
    op.execute('CREATE INDEX ix_vinculos_indices_insumos_tenant_id ON vinculos_indices_insumos (tenant_id)')
    op.execute('\nCREATE TABLE retiros_indices_costos (\n\tobservacion_id UUID, \n\tvinculo_id UUID, \n\tmotivo TEXT NOT NULL, \n\tregistrado_por VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_retiro_un_recurso CHECK ((observacion_id IS NULL) <> (vinculo_id IS NULL)), \n\tUNIQUE (observacion_id), \n\tFOREIGN KEY(observacion_id) REFERENCES observaciones_indices_costos (id) ON DELETE RESTRICT, \n\tUNIQUE (vinculo_id), \n\tFOREIGN KEY(vinculo_id) REFERENCES vinculos_indices_insumos (id) ON DELETE RESTRICT\n)\n\n')
    op.add_column('insumos', sa.Column('actualizacion_precio', postgresql.JSONB(), nullable=True))
    op.create_check_constraint('ck_indice_mes_publicado', 'observaciones_indices_costos',
        "mes = date_trunc('month', mes)::date AND mes < date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date AND publicado_el >= (mes + INTERVAL '1 month')::date AND publicado_el <= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date")
    op.create_check_constraint('ck_vinculo_mes_base', 'vinculos_indices_insumos',
        "mes_base = date_trunc('month', mes_base)::date AND mes_base < date_trunc('month', CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date")
    op.execute("""CREATE FUNCTION indices_costos_evidencia_inmutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'La evidencia de índices es inmutable; registrar una nueva versión o retiro'
        USING ERRCODE = '23514'; END $$""")
    for tabla in ('series_indices_costos', 'observaciones_indices_costos', 'vinculos_indices_insumos', 'retiros_indices_costos'):
        op.execute(f'CREATE TRIGGER tr_{tabla}_inmutable BEFORE UPDATE OR DELETE ON {tabla} FOR EACH ROW EXECUTE FUNCTION indices_costos_evidencia_inmutable()')
        op.execute(f'CREATE TRIGGER tr_{tabla}_no_truncate BEFORE TRUNCATE ON {tabla} FOR EACH STATEMENT EXECUTE FUNCTION indices_costos_evidencia_inmutable()')


def downgrade():
    raise RuntimeError('Migración forward-only: restaurar un respaldo verificado preservando evidencia de índices')
