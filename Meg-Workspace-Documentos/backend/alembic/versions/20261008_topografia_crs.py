"""Preserve survey coordinate frames; store unknown elevation only as NULL z."""
from alembic import op

revision = "20261008_topografia_crs"
down_revision = "20261008_procurement_fencing"
branch_labels = None
depends_on = None


def upgrade():
    # Keep historical horizontal coordinates/SRID and authoritative numeric z.
    # Do not relabel coordinates or invent a transformation for historical rows.
    op.execute("ALTER TABLE puntos_topograficos ALTER COLUMN geom TYPE geometry USING geom")
    op.create_check_constraint("ck_punto_tipo_geometria", "puntos_topograficos",
                               "GeometryType(geom) = 'POINT' AND ST_NDims(geom) IN (2, 3)")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM puntos_topograficos p JOIN levantamientos l
                   ON l.id = p.levantamiento_id WHERE ST_SRID(p.geom) <> l.srid) THEN
            RAISE EXCEPTION 'Hay puntos históricos con SRID distinto al levantamiento; revise la procedencia antes de migrar';
        END IF;
    END $$""")
    op.execute("""CREATE FUNCTION comprobar_srid_punto_topografico() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE marco integer;
    BEGIN
        SELECT l.srid INTO marco FROM levantamientos l JOIN puntos_topograficos p
        ON p.levantamiento_id = l.id WHERE p.id = NEW.id FOR SHARE OF l;
        IF EXISTS (SELECT 1 FROM puntos_topograficos p WHERE p.id = NEW.id
                   AND ST_SRID(p.geom) IS DISTINCT FROM marco) THEN
            RAISE EXCEPTION 'El SRID del punto no corresponde al levantamiento' USING ERRCODE = '23514';
        END IF;
        RETURN NULL;
    END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER ck_punto_marco_levantamiento
        AFTER INSERT OR UPDATE ON puntos_topograficos DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION comprobar_srid_punto_topografico()""")
    op.execute("""CREATE FUNCTION comprobar_srid_levantamiento() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM puntos_topograficos p JOIN levantamientos l
                   ON l.id = p.levantamiento_id WHERE l.id = NEW.id
                   AND ST_SRID(p.geom) IS DISTINCT FROM l.srid) THEN
            RAISE EXCEPTION 'Los puntos no corresponden al SRID del levantamiento' USING ERRCODE = '23514';
        END IF;
        RETURN NULL;
    END $$""")
    op.execute("""CREATE CONSTRAINT TRIGGER ck_levantamiento_marco_puntos
        AFTER UPDATE ON levantamientos DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION comprobar_srid_levantamiento()""")


def downgrade():
    # Mixed SRIDs cannot be squeezed back into the old fixed column safely.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM puntos_topograficos WHERE ST_SRID(geom) <> 6362) THEN
            RAISE EXCEPTION 'No se puede volver a POINTZ/6362 con puntos en otros CRS';
        END IF;
    END $$""")
    op.execute("DROP TRIGGER ck_punto_marco_levantamiento ON puntos_topograficos")
    op.execute("DROP TRIGGER ck_levantamiento_marco_puntos ON levantamientos")
    op.execute("DROP FUNCTION comprobar_srid_punto_topografico()")
    op.execute("DROP FUNCTION comprobar_srid_levantamiento()")
    op.drop_constraint("ck_punto_tipo_geometria", "puntos_topograficos", type_="check")
    op.execute("""ALTER TABLE puntos_topograficos ALTER COLUMN geom TYPE geometry(POINTZ,6362)
        USING ST_SetSRID(ST_MakePoint(x::double precision, y::double precision,
                                     COALESCE(z,0)::double precision),6362)""")
