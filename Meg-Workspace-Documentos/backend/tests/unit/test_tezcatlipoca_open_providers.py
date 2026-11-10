"""Synthetic provider contracts for open commercial-use Tezcatlipoca adapters."""
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from services.aviation.adsb_lol import ADSBLoLClient
from services.transport.osrm_routes import OSRMClient
from services.weather.noaa_nws import NOAAWeatherClient
from services.sar.copernicus_scihub import CopernicusSciHubClient
from services.data_fetcher import DataFetcherEngine
from routers.geo import get_geo_context


@pytest.mark.asyncio
async def test_adsb_lol_validates_geo_coverage_and_provenance():
    received = []
    def handler(request):
        received.append(str(request.url))
        return httpx.Response(200, json={"ac": [
            {"hex": "real-test-synthetic", "flight": "TST001 ", "lat": 19.4, "lon": -99.1,
             "seen_pos": 3, "alt_baro": 10500, "gs": 200},
            {"hex": "outside", "lat": 45, "lon": 40, "seen_pos": 2},
            {"hex": "old", "lat": 19.4, "lon": -99.1, "seen_pos": 900},
        ]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ADSBLoLClient(http=http)
        rows = await client.get_aircraft_in_bbox(19, 20, -100, -99)
        assert len(rows) == 1
        assert rows[0]["flight"] == "TST001"
        assert rows[0]["source"] == "adsb.lol"
        assert rows[0]["altitude_unit"] == "ft"
        assert datetime.fromisoformat(rows[0]["timestamp"])
        assert client.last_request_status == "available"
        assert "api.adsb.lol/v2/lat/" in received[0]
        assert await client.get_aircraft_in_bbox(-90, 90, -180, 180) == []
        assert client.last_request_status == "coverage_limited"
        assert len(received) == 1  # no global-query masquerading as full coverage


@pytest.mark.asyncio
async def test_geo_context_prefers_open_feed_and_does_not_call_paid_adapter(monkeypatch):
    monkeypatch.delenv("TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS", raising=False)
    calls = []
    def handler(request):
        return httpx.Response(200, json={"ac": [
            {"hex": "abc123", "flight": "OPEN1", "lat": 19.4, "lon": -99.1, "seen_pos": 2}
        ]})
    class Paid:
        api_key = "synthetic-paid-key"
        async def get_aircraft_in_bbox(self, *_):
            calls.append("paid")
            raise AssertionError("paid adapter should not be called")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        open_client = ADSBLoLClient(http=http)
        state = SimpleNamespace(adsb_lol=open_client, adsb_exchange=Paid(),
                                data_fetcher=None, ais_connector=None)
        req = SimpleNamespace(app=SimpleNamespace(state=state), state=SimpleNamespace(
            tenant_id="t", megalodon_user_id="u"))
        result = await get_geo_context(
            lat_min=19, lat_max=20, lon_min=-100, lon_max=-99,
            earthquake_days=1, earthquake_magnitude=2.5,
            limit=10, req=req, current_user=None, _rate_limit=True)
        assert not calls
        assert len(result["aircraft"]) == 1
        assert result["aircraft"][0]["source"] == "adsb_lol"
        assert result["sources"]["adsb_lol"]["license"] == "ODbL-1.0"
        assert result["sources"]["adsb_exchange"]["status"] == "disabled_by_default"


@pytest.mark.asyncio
async def test_osrm_self_hosted_converts_seconds_and_rejects_invalid_profiles():
    urls = []
    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={"code": "Ok", "routes": [{
            "distance": 1000.3, "duration": 62.7,
            "geometry": {"coordinates": [[-99.1, 19.4], [-99.2, 19.5]]}}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OSRMClient(base_url="http://osrm:5000", http=http)
        route = await client.get_route(19.4, -99.1, 19.5, -99.2)
        assert route["source"] == "osrm_self_hosted"
        assert route["distance_m"] == 1000.3
        assert route["time_ms"] == 62700
        assert "/route/v1/driving/-99.100000,19.400000;-99.200000,19.500000" in urls[0]
        assert (await client.get_route(19.4, -99.1, 19.5, -99.2, "foot"))["status"] == "unsupported_profile"
        assert len(urls) == 1
        assert (await OSRMClient(base_url="", http=http).get_route(19.4, -99.1, 19.5, -99.2))["status"] == "config_required"


@pytest.mark.asyncio
async def test_noaa_forecast_validates_upstream_url():
    def handler(request):
        if "/points/" in str(request.url):
            return httpx.Response(200, json={"properties": {"forecast": "http://127.0.0.1/private"}})
        raise AssertionError("must not follow untrusted URL")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = NOAAWeatherClient(http=http)
        assert (await client.forecast(38.88, -77.03))["status"] == "unavailable"
        assert (await client.forecast(91, 0))["status"] == "invalid_coordinates"


@pytest.mark.asyncio
async def test_noaa_forecast_in_supported_region():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if "/points/" in str(request.url):
            return httpx.Response(200, json={"properties": {
                "forecast": "https://api.weather.gov/gridpoints/LWX/100,70/forecast"}})
        return httpx.Response(200, json={"properties": {"periods": [
            {"name": "Today", "temperature": 22, "temperatureUnit": "C"}]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await NOAAWeatherClient(http=http).forecast(38.88, -77.03)
        assert result["status"] == "available"
        assert result["source"] == "noaa_nws"
        assert len(result["periods"]) == 1
        assert len(seen) == 2


@pytest.mark.asyncio
async def test_cdse_filters_only_sentinel_and_bounds():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"value": [{
            "Id": "a-b-c", "Name": "S1A_IW_GRDH", "ContentDate": {"Start": "2026-11-01T00:00:00Z"},
            "GeoFootprint": {"type": "Polygon", "coordinates": []}
        }]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = CopernicusSciHubClient(http=http)
        rows = await client.search_sentinel1(
            [-100, 19, -99, 20], "2026-11-01", "2026-11-08", "GRD", 10)
        assert rows[0]["source"] == "copernicus_data_space"
        params = requests[0].url.params
        assert "Collection/Name eq 'SENTINEL-1'" in params["$filter"]
        assert "Intersects" in params["$filter"]
        assert params["$top"] == "10"
        assert (await client.search_sentinel1([200, 0, 201, 1]))[0]["error"]
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_legacy_hosted_jobs_not_scheduled_by_default(monkeypatch):
    monkeypatch.delenv("TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS", raising=False)
    fetcher = DataFetcherEngine()
    try:
        scheduled = {j[0] for j in fetcher.jobs}
        assert "fetch_usgs" in scheduled
        assert not {"fetch_opensky", "fetch_nws", "fetch_openaq"} & scheduled
        assert fetcher.source_status["nws"]["status"] == "disabled_by_default"
    finally:
        await fetcher.close()
