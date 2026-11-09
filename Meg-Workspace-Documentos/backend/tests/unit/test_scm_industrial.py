"""Tests industriales para Supply Chain Risk Management.

Verifica:
- Cálculo de risk score ponderado
- Construcción de vendor profile con fuentes reales
- Filtros de listado
- Cache TTL
- Recomendaciones basadas en datos reales
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tezcatlipoca.routers.scm import (
    _calculate_risk_score, _build_vendor_profile, _generate_recommendations,
    _generate_aggregate_recommendations, _cache_get, _cache_set, CacheEntry,
    VENDOR_REGISTRY, list_vendors, get_vendor, get_supply_chain_risks,
    assess_vendor, VendorProfile,
)


class TestRiskScoreCalculation:
    def test_zero_risk(self):
        score = _calculate_risk_score(0, 0, 0, 0, 0, False)
        assert score == 0.0

    def test_critical_cves_only(self):
        score = _calculate_risk_score(5, 5, 0, 0, 0, False)
        assert score == 4.0  # 5 * 0.8 capped at 4.0

    def test_shodan_exposure(self):
        score = _calculate_risk_score(0, 0, 0, 500, 0, False)
        assert score == 2.5  # 500/200 capped at 2.5

    def test_kev_presence(self):
        score = _calculate_risk_score(0, 0, 3, 0, 0, False)
        assert score == 2.0  # 3 * 1.0 capped at 2.0

    def test_feodo_and_greynoise(self):
        score = _calculate_risk_score(0, 0, 0, 0, 2, True)
        assert score == 1.5  # 2*0.5=1.0 + 0.5 = 1.5 capped

    def test_max_risk_score(self):
        score = _calculate_risk_score(100, 100, 100, 100000, 100, True)
        assert score == 10.0  # capped at 10

    def test_risk_score_rounding(self):
        score = _calculate_risk_score(1, 1, 1, 200, 1, False)
        assert isinstance(score, float)
        assert 0 <= score <= 10


class TestCache:
    def test_cache_set_and_get(self):
        _cache_set("test_key", {"data": 123}, ttl=60)
        result = _cache_get("test_key")
        assert result == {"data": 123}

    def test_cache_expiration(self):
        from datetime import datetime, timezone, timedelta
        import tezcatlipoca.routers.scm as scm_module
        scm_module._cache["expired"] = CacheEntry(data="old", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        result = _cache_get("expired")
        assert result is None
        assert "expired" not in scm_module._cache

    def test_cache_miss(self):
        result = _cache_get("nonexistent_key_12345")
        assert result is None


class TestVendorProfileBuilding:
    @pytest.mark.asyncio
    async def test_build_microsoft_profile(self, monkeypatch):
        """Construcción de perfil Microsoft con mocks de fuentes."""
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_cisa_kev", AsyncMock(return_value={
            "count": 5, "cves": [{"vulnerability": "CVE-2024-0001"}, {"vulnerability": "CVE-2024-0002 critical"}],
            "known_ransomware": 1, "source": "cisa_kev"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_shodan", AsyncMock(return_value={
            "hosts": 250, "services": ["80", "443"], "source": "shodan"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_feodo", AsyncMock(return_value={
            "malicious_ips": [], "count": 0, "source": "feodo_tracker"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_greynoise", AsyncMock(return_value={
            "noise_ips": 0, "source": "greynoise"
        }))

        profile = await _build_vendor_profile("microsoft")
        assert profile.id == "microsoft"
        assert profile.name == "Microsoft"
        assert profile.cve_count == 5
        assert profile.critical_cves == 1
        assert profile.shodan_exposed_hosts == 250
        assert profile.data_quality == "complete"
        assert "cisa_kev" in profile.sources
        assert "shodan" in profile.sources

    @pytest.mark.asyncio
    async def test_build_vendor_not_found(self):
        """Vendor no registrado debe lanzar 404."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _build_vendor_profile("nonexistent_vendor_xyz")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_build_with_degraded_sources(self, monkeypatch):
        """Si solo 1 fuente responde, data_quality debe ser 'degraded'."""
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_cisa_kev", AsyncMock(return_value={
            "count": 1, "cves": [], "known_ransomware": 0, "source": "cisa_kev"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_shodan", AsyncMock(return_value={
            "hosts": 0, "services": [], "source": "shodan", "error": "timeout"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_feodo", AsyncMock(return_value={
            "malicious_ips": [], "count": 0, "source": "feodo_tracker", "error": "timeout"
        }))
        monkeypatch.setattr("tezcatlipoca.routers.scm._fetch_greynoise", AsyncMock(return_value={
            "noise_ips": 0, "source": "greynoise", "error": "timeout"
        }))

        profile = await _build_vendor_profile("cisco")
        assert profile.data_quality == "degraded"
        assert profile.sources == ["cisa_kev"]


class TestRecommendations:
    def test_critical_cve_recommendation(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=8.0, cve_count=5, critical_cves=3, kev_count=0,
            shodan_exposed_hosts=50, feodo_ips=0, greynoise_noise=False,
            data_quality="complete", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("CRÍTICO" in r and "3 CVEs críticos" in r for r in recs)

    def test_kev_recommendation(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=6.0, cve_count=2, critical_cves=0, kev_count=2,
            shodan_exposed_hosts=50, feodo_ips=0, greynoise_noise=False,
            data_quality="complete", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("KEV" in r for r in recs)

    def test_feodo_recommendation(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=9.0, cve_count=0, critical_cves=0, kev_count=0,
            shodan_exposed_hosts=50, feodo_ips=3, greynoise_noise=False,
            data_quality="complete", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("Feodo" in r for r in recs)

    def test_greynoise_recommendation(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=5.0, cve_count=0, critical_cves=0, kev_count=0,
            shodan_exposed_hosts=50, feodo_ips=0, greynoise_noise=True,
            data_quality="complete", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("GreyNoise" in r for r in recs)

    def test_degraded_quality_warning(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=2.0, cve_count=0, critical_cves=0, kev_count=0,
            shodan_exposed_hosts=50, feodo_ips=0, greynoise_noise=False,
            data_quality="degraded", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("degradada" in r for r in recs)

    def test_no_risks_acceptable(self):
        profile = VendorProfile(
            id="test", name="Test", category="software",
            risk_score=1.0, cve_count=0, critical_cves=0, kev_count=0,
            shodan_exposed_hosts=10, feodo_ips=0, greynoise_noise=False,
            data_quality="complete", sources=[]
        )
        recs = _generate_recommendations(profile, {"cves": []})
        assert any("aceptable" in r for r in recs)

    def test_aggregate_critical_vendors(self):
        profiles = [
            VendorProfile(id="a", name="A", category="software", risk_score=8.0, cve_count=0, critical_cves=0, kev_count=0, shodan_exposed_hosts=0, feodo_ips=0, greynoise_noise=False, data_quality="complete", sources=[]),
            VendorProfile(id="b", name="B", category="software", risk_score=7.5, cve_count=0, critical_cves=0, kev_count=0, shodan_exposed_hosts=0, feodo_ips=0, greynoise_noise=False, data_quality="complete", sources=[]),
        ]
        recs = _generate_aggregate_recommendations(profiles)
        assert any("2 vendor(s) con riesgo CRÍTICO" in r for r in recs)


class TestVendorRegistry:
    def test_all_vendors_have_required_fields(self):
        for vid, vdata in VENDOR_REGISTRY.items():
            assert "name" in vdata
            assert "category" in vdata
            assert "products" in vdata
            assert isinstance(vdata["products"], list)

    def test_vendor_categories_valid(self):
        valid = {"software", "security", "infrastructure", "cloud", "hardware", "devops", "networking", "iot", "other", "it-management"}
        for vdata in VENDOR_REGISTRY.values():
            assert vdata["category"] in valid
