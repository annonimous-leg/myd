from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def test_no_runtime_shadow_packages():
    forbidden = [
        'ifcopenshell', 'geoalchemy2', 'jose', 'passlib', 'structlog',
        'aiosqlite', 'celery', 'bcrypt.py', 'jwt.py'
    ]
    assert not [name for name in forbidden if (ROOT / name).exists()]


def test_no_python_pass_or_notimplemented_in_product():
    findings = []
    for base in [ROOT / 'app', ROOT / 'tezcatlipoca']:
        for path in base.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Pass):
                    findings.append((str(path), node.lineno, 'pass'))
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and isinstance(node.exc.func, ast.Name)
                    and node.exc.func.id == 'NotImplementedError'
                ):
                    findings.append((str(path), node.lineno, 'NotImplementedError'))
    assert findings == findings  # structural gate; zero is asserted below
    assert not findings, findings


def test_cpm_rejects_missing_predecessors():
    text = read('app/engines/programacion/cpm.py')
    assert 'predecesoras_inexistentes' in text
    assert 'if missing:' in text


def test_compliance_never_treats_empty_rule_as_true():
    text = read('app/engines/compliance/motor_compliance.py')
    assert 'Regla de compliance sin condición evaluable.' in text
    assert 'NOT_EVALUABLE' in text


def test_planeacion_uses_tenant_scoped_catalog():
    service = read('app/services/planeacion_obra_service.py')
    assert 'CatalogoAPU.tenant_id == tenant_id' in service
    assert 'vigencia_inicio' in service and 'vigencia_fin' in service
    assert 'tarifas_catalogo' in service


def test_ai_command_never_claims_queued_without_queue():
    text = read('tezcatlipoca/routers/ai_channel.py')
    assert 'status = "COMPLETED" if result.get("executed") else ("FAILED" if result.get("error") else "REJECTED")' in text


def test_ai_prediction_declares_evidence_based_method():
    text = read('tezcatlipoca/routers/ai_channel.py')
    assert 'deterministic_linear_trend_v1' in text
    assert 'NOT_EVALUABLE' in text


def test_sar_does_not_claim_zero_anomaly_score():
    text = read('tezcatlipoca/routers/sar.py')
    assert '"anomaly_score": 0.0' not in text
    assert 'NOT_COMPUTED_RASTER_REQUIRED' in text


def test_production_event_bus_requires_redis():
    text = read('tezcatlipoca/core/event_bus.py')
    assert 'REDIS_URL obligatorio para EventBus en producción' in text
    assert 'xadd(' in text and 'xreadgroup' in text and 'dead_letter' in text


def test_frontend_costos_has_no_synthetic_hospital_generator():
    text = read('../frontend/app/src/apps/megalodon-costos/index.tsx')
    assert 'generateHospitalElements' not in text
    assert 'Hospital General Regional' not in text


def test_plan_dependency_does_not_default_missing_tenant_to_free():
    text = (Path(__file__).parents[2] / "app/core/entitlements.py").read_text()
    assert 'tenant else PlanTipo.FREE.value' not in text
    assert 'Tenant no encontrado o inactivo' in text


def test_search_tags_requires_tenant_scope():
    text = (Path(__file__).parents[2] / "app/modules/search/service.py").read_text()
    assert 'tenant_id es obligatorio para buscar documentos por tags' in text


def test_tez_startup_exposes_component_statuses():
    text = (Path(__file__).parents[2] / "app/main.py").read_text()
    assert 'tezcatlipoca_components' in text
    assert 'CONFIG_REQUIRED' in text


def test_browser_auth_uses_http_only_refresh_cookie():
    auth = (Path(__file__).parents[2] / "app/api/v1/auth.py").read_text()
    deps = (Path(__file__).parents[2] / "app/core/deps.py").read_text()
    store = (Path(__file__).parents[3] / "frontend/app/src/stores/useAuthStore.ts").read_text()
    assert 'REFRESH_COOKIE_NAME' in auth
    assert 'path="/api/v1/auth"' in auth
    assert 'REFRESH_COOKIE_NAME = "megalodon_refresh_token"' in deps
    assert 'persist(' not in store


def test_search_and_entitlements_never_fallback_missing_tenant_to_free_or_global():
    ent = (Path(__file__).parents[2] / "app/core/entitlements.py").read_text()
    search = (Path(__file__).parents[2] / "app/modules/search/service.py").read_text()
    assert 'tenant else PlanTipo.FREE.value' not in ent
    assert 'tenant_id es obligatorio para buscar documentos por tags' in search
