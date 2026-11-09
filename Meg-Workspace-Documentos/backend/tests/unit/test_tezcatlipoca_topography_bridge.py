from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_geo_context_endpoint_exists_and_is_authenticated():
    text = (ROOT / "tezcatlipoca/routers/geo.py").read_text(encoding="utf-8")
    assert '@router.get("/context")' in text
    assert 'Depends(get_current_user)' in text
    assert 'req.state' in text
    assert 'aircraft' in text and 'ships' in text and 'earthquakes' in text


def test_dashboard_no_longer_advertises_unconnected_geo_hub():
    text = (ROOT.parent / "frontend/app/src/components/Home.tsx").read_text(encoding="utf-8")
    assert 'Pendiente de conectar a Tezcatlipoca (Geo Hub)' not in text
    assert 'tezcatlipoca.telemetry()' in text


def test_entitlements_ui_fails_closed_when_backend_unknown():
    text = (ROOT.parent / "frontend/app/src/stores/useEntitlementsStore.ts").read_text(encoding="utf-8")
    assert 'if (!get().cargado) return false;' in text
    assert 'if (!modulo) return false;' in text
