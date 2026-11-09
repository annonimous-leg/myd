"""Protect IFC element identity and BIM budget links without deleting historical evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20261006_bim_integridad'
down_revision = '20261005_ingesta_inegi'
branch_labels = None
depends_on = None


def upgrade():
    # Historical conflicts require an explicit repair, never pick a mapping silently.
    bind = op.get_bind()
    duplicates = bind.execute(sa.text('SELECT modelo_id, global_id FROM elementos_bim GROUP BY modelo_id, global_id HAVING count(*) > 1 LIMIT 1')).first()
    invalid = bind.execute(sa.text('''SELECT e.id FROM elementos_bim e
        JOIN modelos_bim m ON m.id=e.modelo_id JOIN partidas p ON p.id=e.partida_id
        JOIN presupuestos b ON b.id=p.presupuesto_id
        WHERE m.tenant_id<>b.tenant_id OR m.expediente_id<>b.expediente_id LIMIT 1''')).first()
    if duplicates or invalid:
        raise RuntimeError('BIM histórico inconsistente: reparar duplicados/enlaces con respaldo antes de aplicar esta migración')
    op.create_foreign_key('fk_modelobim_tenant_expediente', 'modelos_bim', 'expedientes_obra',
        ['tenant_id', 'expediente_id'], ['tenant_id', 'id'])
    op.create_unique_constraint('uq_elementobim_modelo_global', 'elementos_bim', ['modelo_id', 'global_id'])
    op.execute("""CREATE FUNCTION bim_validar_elemento() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE model record; budget record;
    BEGIN
        SELECT tenant_id, expediente_id INTO model FROM modelos_bim WHERE id=NEW.modelo_id FOR SHARE;
        IF NEW.partida_id IS NOT NULL THEN
            SELECT p.tenant_id AS partida_tenant, b.tenant_id, b.expediente_id INTO budget
                FROM partidas p JOIN presupuestos b ON b.id=p.presupuesto_id
                WHERE p.id=NEW.partida_id FOR SHARE OF p,b;
            IF budget.tenant_id<>model.tenant_id OR budget.partida_tenant<>model.tenant_id
                OR budget.expediente_id<>model.expediente_id THEN
                RAISE EXCEPTION 'BIM: partida fuera del tenant o expediente' USING ERRCODE='23514';
            END IF;
        END IF;
        RETURN NEW;
    END; $$""")
    op.execute("""CREATE TRIGGER tr_elementos_bim_enlace BEFORE INSERT OR UPDATE OF modelo_id,partida_id
        ON elementos_bim FOR EACH ROW EXECUTE FUNCTION bim_validar_elemento()""")
    op.execute("""CREATE FUNCTION bim_validar_padre() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE link record; budget record;
    BEGIN
        IF TG_TABLE_NAME='modelos_bim' THEN
            FOR link IN SELECT b.tenant_id,b.expediente_id,p.tenant_id AS partida_tenant
                FROM elementos_bim e JOIN partidas p ON p.id=e.partida_id
                JOIN presupuestos b ON b.id=p.presupuesto_id WHERE e.modelo_id=OLD.id FOR SHARE OF p,b
            LOOP
                IF link.tenant_id<>NEW.tenant_id OR link.partida_tenant<>NEW.tenant_id OR link.expediente_id<>NEW.expediente_id THEN
                    RAISE EXCEPTION 'BIM: partida fuera del tenant o expediente' USING ERRCODE='23514';
                END IF;
            END LOOP;
        ELSIF TG_TABLE_NAME='presupuestos' THEN
            FOR link IN SELECT m.tenant_id,m.expediente_id,p.tenant_id AS partida_tenant
                FROM elementos_bim e JOIN partidas p ON p.id=e.partida_id
                JOIN modelos_bim m ON m.id=e.modelo_id WHERE p.presupuesto_id=OLD.id FOR SHARE OF m,p
            LOOP
                IF link.tenant_id<>NEW.tenant_id OR link.partida_tenant<>NEW.tenant_id OR link.expediente_id<>NEW.expediente_id THEN
                    RAISE EXCEPTION 'BIM: partida fuera del tenant o expediente' USING ERRCODE='23514';
                END IF;
            END LOOP;
        ELSE
            SELECT tenant_id,expediente_id INTO budget FROM presupuestos WHERE id=NEW.presupuesto_id FOR SHARE;
            FOR link IN SELECT m.tenant_id,m.expediente_id FROM elementos_bim e
                JOIN modelos_bim m ON m.id=e.modelo_id WHERE e.partida_id=OLD.id FOR SHARE OF m
            LOOP
                IF link.tenant_id<>NEW.tenant_id OR link.tenant_id<>budget.tenant_id OR link.expediente_id<>budget.expediente_id THEN
                    RAISE EXCEPTION 'BIM: partida fuera del tenant o expediente' USING ERRCODE='23514';
                END IF;
            END LOOP;
        END IF;
        RETURN NEW;
    END; $$""")
    for table, columns in [('modelos_bim','tenant_id,expediente_id'),
                           ('presupuestos','tenant_id,expediente_id'), ('partidas','tenant_id,presupuesto_id')]:
        op.execute(f'CREATE TRIGGER tr_{table}_bim_enlace BEFORE UPDATE OF {columns} ON {table} FOR EACH ROW EXECUTE FUNCTION bim_validar_padre()')


def downgrade():
    op.execute('DROP TRIGGER tr_elementos_bim_enlace ON elementos_bim')
    for table in ['modelos_bim', 'partidas', 'presupuestos']:
        op.execute(f'DROP TRIGGER tr_{table}_bim_enlace ON {table}')
    op.execute('DROP FUNCTION bim_validar_elemento()')
    op.execute('DROP FUNCTION bim_validar_padre()')
    op.drop_constraint('fk_modelobim_tenant_expediente', 'modelos_bim', type_='foreignkey')
    op.drop_constraint('uq_elementobim_modelo_global', 'elementos_bim', type_='unique')
