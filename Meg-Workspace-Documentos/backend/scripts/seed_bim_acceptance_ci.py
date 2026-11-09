"""Synthetic acceptance identities/catalog in disposable CI staging only."""
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from hashlib import sha256
from uuid import UUID, uuid4


async def main():
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('ENVIRONMENT') != 'staging':
        raise SystemExit('Seeding is confined to disposable GitHub CI staging.')
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    if url.database != 'bim_acceptance' or url.host not in ('localhost','127.0.0.1'):
        raise SystemExit('Dedicated local acceptance database required.')
    import app.models
    from app.models.base import AsyncSessionLocal, engine
    from app.models.user import Tenant, User, UserRole
    from app.models.entitlements import Suscripcion, EstadoSuscripcion
    from app.models.catalogo_apu import CatalogoAPU
    from app.models.catalogo_conceptos import CatalogoFuente, ConceptoCatalogo, InsumoCatalogo
    from app.models.indices_costos import SerieIndiceCosto, ObservacionIndiceCosto, VinculoIndiceInsumo
    from app.models.procurement import JurisdictionProfile, LegalSource, LegalArticle, LegalRule
    from app.services.auth_service import AuthService
    from app.services.entitlements_service import EntitlementsService
    if len(sys.argv) == 3 and sys.argv[1] in ('--programs-for', '--projects-after'):
        from sqlalchemy import select
        from app.models.expediente import ExpedienteObra
        from app.services.programacion_service import ProgramacionService
        credentials = json.loads(Path(os.environ['BIM_ACCEPTANCE_CREDENTIALS']).read_text())
        async with AsyncSessionLocal() as db:
            user = await db.scalar(select(User).where(User.email == credentials['reviewer']))
            obra = await db.get(ExpedienteObra, UUID(sys.argv[2]))
            if not user or not obra or obra.tenant_id != user.tenant_id:
                raise SystemExit('Acceptance obra ownership required.')
            if sys.argv[1] == '--projects-after':
                db.add_all([ExpedienteObra(tenant_id=user.tenant_id, responsable_id=user.id,
                    identificador=f'CI-PAGE-{uuid4().hex[:16]}', titulo=f'Expediente posterior CI {number}',
                    organo='CI sintético', unidad_administrativa='CI', serie_documental='CI',
                    subserie_documental='CI') for number in range(100)])
                await db.commit()
                await engine.dispose()
                return
            service = ProgramacionService(db, user.tenant_id)
            for number in range(21):
                await service.crear_programa(expediente_id=obra.id,nombre=f'Programa previo {number}',
                    descripcion='Synthetic acceptance pagination fixture',
                    fecha_inicio=datetime(2026,10,6,tzinfo=timezone.utc),
                    actividades_data=[{'id':'A','nombre':'Actividad previa','duracion':1}],
                    creado_por_id=user.id,tenant_id=user.tenant_id)
        await engine.dispose()
        return
    if len(sys.argv) != 1:
        raise SystemExit('Unsupported acceptance seed arguments.')
    password = uuid4().hex
    import ifcopenshell
    document = ifcopenshell.open(str(Path(__file__).parents[1] / 'tests/fixtures/ifc/wall_millimetres.ifc'))
    document.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='Faltante de medición CI')
    partial_ifc = Path('/tmp/megalodon-partial-acceptance.ifc')
    document.write(str(partial_ifc))
    async with AsyncSessionLocal() as db:
        ahora = datetime.now(timezone.utc)
        vencimiento = ahora + timedelta(days=31)
        tenant = Tenant(name='BIM acceptance (synthetic)', slug='bim-ci-'+uuid4().hex,
            plan='ENTERPRISE', plan_vencimiento=vencimiento, is_active=True)
        if EntitlementsService(db).calcular_plan_efectivo(tenant) != 'ENTERPRISE':
            raise SystemExit('The synthetic acceptance plan must be effective before starting the flow.')
        db.add(tenant)
        await db.flush()
        db.add(Suscripcion(tenant_id=tenant.id, plan='ENTERPRISE', proveedor='CI_SYNTHETIC',
            estado=EstadoSuscripcion.ACTIVA.value, fecha_inicio=ahora, fecha_fin=vencimiento,
            monto=0, moneda='MXN', metadatos={'synthetic':True, 'purpose':'disposable browser acceptance; no payment'}))
        service = AuthService(db)
        users = [User(email=uuid4().hex+'@bim-ci.local', full_name='CI '+role.value,
            role=role, tenant_id=tenant.id, is_active=True, is_verified=True,
            hashed_password=service.hash_password(password)) for role in (UserRole.REVISOR, UserRole.LECTOR, UserRole.TECNICO)]
        db.add_all(users)
        await db.flush()

        # Synthetic jurisdiction pack exists only in this disposable CI database.
        # It proves profile/source/article/rule bindings, never acts as an official legal source.
        profile_code = 'CI-BIDDER-PROPOSAL'
        synthetic_rule_text = (
            'Disposable CI-only rule fixture for the bidder workspace. '
            'It has no legal effect and must never be presented as an official source.'
        )
        profile = JurisdictionProfile(
            tenant_id=tenant.id,
            code=profile_code,
            authority='CI synthetic profile (not an issuing authority)',
            government_level='FEDERAL',
            matter='PUBLIC_WORKS',
            portal_code='CI_SYNTHETIC_ONLY',
            profile_version=1,
            ruleset={
                'ready_for_execution': True,
                'regime_family': 'PUBLIC_WORKS',
                'selection_label': 'CI synthetic bidder-only profile',
                'allowed_procedures': ['LICITACION_PUBLICA'],
                'allowed_contract_types': ['UNIT_PRICES'],
                'allowed_evaluation_criteria': ['PUNTOS_Y_PORCENTAJES'],
                'allowed_funding_sources': ['FEDERAL'],
                'allowed_legal_regimes': ['CI_SYNTHETIC_ONLY'],
                'allowed_object_classes': ['PUBLIC_WORKS'],
                'required_approval_roles': ['revisor'],
            },
            templates={
                'requirement_extraction': {
                    'required_source_roles': ['CONVOCATORIA'],
                    'source_roles': {
                        'CONVOCATORIA': {
                            'formats': {
                                'TXT': {
                                    'sections': [{
                                        'name': 'REQUISITOS DE PARTICIPACIÓN',
                                        'headings': ['REQUISITOS DE PARTICIPACIÓN'],
                                        'stop_headings': ['ANEXOS'],
                                        'item_pattern': r'^\s*\d+[.)]\s+(?P<description>.+?)\s*$',
                                        'category': 'ADMINISTRATIVO',
                                    }],
                                },
                            },
                        },
                    },
                },
            },
            active=True,
            creado_por_id=users[2].id,
            actualizado_por_id=users[2].id,
        )
        source_bytes = synthetic_rule_text.encode('utf-8')
        legal_source = LegalSource(
            tenant_id=tenant.id,
            authority='CI synthetic fixture',
            title='Fuente jurídica sintética para pruebas de integración',
            citation='CI ONLY — NO LEGAL EFFECT',
            source_uri='https://example.invalid/megalodon-ci/synthetic-rule.txt',
            publication_date='2026-10-28',
            effective_from='2026-10-01',
            version='CI-SYNTHETIC-1',
            content_hash=sha256(source_bytes).hexdigest(),
            jurisdiction_code=profile_code,
            status='ACTIVE',
            creado_por_id=users[2].id,
            actualizado_por_id=users[2].id,
        )
        db.add_all([profile, legal_source])
        await db.flush()
        legal_article = LegalArticle(
            source_id=legal_source.id,
            article_code='CI-ONLY-ARTICLE-1',
            title='Synthetic CI fixture',
            summary=synthetic_rule_text,
            effective_from='2026-10-01',
            content_hash=sha256((synthetic_rule_text + ' article').encode('utf-8')).hexdigest(),
            status='ACTIVE',
        )
        db.add(legal_article)
        await db.flush()
        db.add(LegalRule(
            tenant_id=tenant.id,
            rule_id='CI-BIDDER-BASELINE',
            jurisdiction_code=profile_code,
            domain='PROCEDURE',
            procedure_type='LICITACION_PUBLICA',
            source_id=legal_source.id,
            article_id=legal_article.id,
            source_version=legal_source.version,
            condition={'type': 'CI_ONLY', 'authority': 'SYNTHETIC'},
            requirement={'code': 'CI-SOURCE-CHECK', 'description': synthetic_rule_text},
            validation={'type': 'HUMAN_REVIEW_REQUIRED'},
            severity='BLOCKER',
            effective_from='2026-10-01',
            rule_version=1,
            active=True,
            creado_por_id=users[2].id,
            actualizado_por_id=users[2].id,
        ))
        db.add(CatalogoAPU(tenant_id=tenant.id, clave='CI-WALL-ONLY',
            descripcion='Muro de prueba sintética CI', tipo='CONCEPTO', unidad='m3',
            precio_unitario=125, fuente='CI_SYNTHETIC_NOT_MARKET_PRICE'))
        db.add(CatalogoAPU(tenant_id=tenant.id, clave='CI-EARTHWORK',
            descripcion='Movimiento de tierras sintético CI', tipo='CONCEPTO', unidad='m3',
            precio_unitario=100, fuente='CI_SYNTHETIC_NOT_MARKET_PRICE'))
        fuente = CatalogoFuente(nombre='CI sintético: catálogo de aceptación', tipo='CUSTOM',
            vigencia_inicio='2020-01-01', vigencia_fin='2020-12-31', moneda='MXN', activo=True)
        db.add(fuente); await db.flush()
        material = InsumoCatalogo(fuente_id=fuente.id, clave='CI-INDEXED',
            descripcion='Material sintético indexado CI', tipo='MATERIAL', unidad='kg',
            precio_unitario=100, incluye_iva=False, activo=True)
        db.add(material)
        db.add(ConceptoCatalogo(fuente_id=fuente.id, clave='CI-CATALOG',
            descripcion='Concepto sintético CI', unidad='kg', precio_unitario=100, activo=True))
        evidencia = {'url':'https://example.invalid/ci-no-oficial.pdf', 'sha256':'a'*64,
            'localizador':'Fixture sintética; no es publicación INEGI ni precio de mercado'}
        serie = SerieIndiceCosto(codigo='CI-NOT-OFFICIAL', version_metodologia='TEST-1',
            nombre='Índice sintético CI', region='NACIONAL', condiciones_precio='Material sintético sin IVA',
            periodo_referencia='enero 2020=100', evidencia=evidencia, registrado_por=str(users[0].id))
        db.add(serie); await db.flush()
        for mes, valor, publicado, doc in [(date(2020,1,1),100,date(2020,2,10),'a'),
                                          (date(2020,8,1),115,date(2020,9,10),'b')]:
            db.add(ObservacionIndiceCosto(serie_id=serie.id, mes=mes, valor=valor,
                publicado_el=publicado, documento_sha256=doc*64,
                evidencia={**evidencia,'sha256':doc*64}, registrado_por=str(users[0].id)))
        vinculo = VinculoIndiceInsumo(tenant_id=tenant.id, insumo_id=material.id,
            serie_id=serie.id, mes_base=date(2020,1,1), precio_original=100,
            insumo_original={'clave':material.clave,'descripcion':material.descripcion,
                'unidad':'kg','tipo':'MATERIAL','moneda':'MXN'},
            fundamento='Correspondencia sintética exclusivamente para aceptación CI',
            evidencia=evidencia, revisado_por=str(users[0].id))
        db.add(vinculo)
        await db.commit()
        await EntitlementsService(db).sembrar_planes_default()
        await EntitlementsService(db).sembrar_modulos_default()
        destination = Path(os.environ['BIM_ACCEPTANCE_CREDENTIALS'])
        from tests.fixtures.catalog_import import make_synthetic_package
        from zipfile import ZipFile, ZIP_DEFLATED
        package, originals, _ = make_synthetic_package(Path('/tmp/megalodon-catalog-fixture'))
        original_target = Path(os.environ['CATALOGO_ORIGINALES_DIR'])
        original_target.mkdir(parents=True, exist_ok=True)
        for pdf in originals.glob('*.pdf'):
            (original_target / pdf.name).write_bytes(pdf.read_bytes())
        package_zip = Path('/tmp/megalodon-catalog-package.zip')
        with ZipFile(package_zip, 'w', ZIP_DEFLATED) as archive:
            for path in package.rglob('*'):
                if path.is_file(): archive.write(path, path.relative_to(package))
        destination.write_text(json.dumps({'reviewer':users[0].email, 'reader':users[1].email,
            'bidder':users[2].email, 'bidder_profile_code':profile_code,
            'password':password, 'catalog_description':'Muro de prueba sintética CI',
            'indexed_material':str(vinculo.id),
            'partial_ifc':str(partial_ifc), 'catalog_package': str(package_zip)}))
        destination.chmod(0o600)
    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
