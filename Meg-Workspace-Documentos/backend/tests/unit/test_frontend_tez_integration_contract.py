from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_has_tez_bridge_client_and_hub():
    client = (ROOT.parent / "frontend/app/src/lib/megalodon-client.ts").read_text(encoding="utf-8")
    registry = (ROOT.parent / "frontend/app/src/stores/useAppRegistry.ts").read_text(encoding="utf-8")
    hub = (ROOT.parent / "frontend/app/src/apps/tezcatlipoca-hub/index.tsx").read_text(encoding="utf-8")
    topo = (ROOT.parent / "frontend/app/src/apps/topografia/index.tsx").read_text(encoding="utf-8")
    topo_feed = (ROOT.parent / "frontend/app/src/apps/topografia/components/TezcatlipocaFeedPanel.tsx").read_text(encoding="utf-8")
    home = (ROOT.parent / "frontend/app/src/components/Home.tsx").read_text(encoding="utf-8")
    assert 'private async requestTez' in client
    assert 'geoContext' in client and 'osintLookup' in client and 'cyberCisaStats' in client and 'sarScenes' in client
    assert "id: 'tezcatlipoca-hub'" in registry
    assert 'megalodonClient.tezcatlipoca.geoContext' in hub
    assert 'megalodonClient.tezcatlipoca.telemetry()' in home
    assert "MapaPanel" in topo
    assert 'megalodonClient.tezcatlipoca.geoContext' in topo_feed
