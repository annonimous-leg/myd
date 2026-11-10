"""Synthetic provider-contract regressions; live acceptance is a separate check."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from services.data_fetcher import DataFetcherEngine
from services.aviation.adsb_exchange import ADSBExchangeClient
from routers.geo import get_geo_context, get_geo_earthquakes, get_geo_flights, _bounds


def event(identifier, hours_ago=1, lat=19.4, lon=-99.1, mag=4.2):
    observed = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {"type": "Feature", "id": identifier,
            "geometry": {"type": "Point", "coordinates": [lon, lat, 8]},
            "properties": {"mag": mag, "time": observed.timestamp() * 1000,
                           "place": "Synthetic fixture", "url": "https://example.test/event"}}


def request(fetcher=None, adsb=None, ais=None):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(data_fetcher=fetcher, adsb_exchange=adsb, ais_connector=ais)),
        state=SimpleNamespace(tenant_id="tenant-fixture", megalodon_user_id="user-fixture"))


async def context(req, **overrides):
    args = dict(lat_min=19, lat_max=20, lon_min=-100, lon_max=-99, earthquake_days=1,
                earthquake_magnitude=2.5, limit=100, req=req, current_user=None, _rate_limit=True)
    args.update(overrides)
    return await get_geo_context(**args)


async def mock_fetcher(handler):
    engine = DataFetcherEngine()
    await engine.http.aclose()
    engine.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return engine


@pytest.mark.asyncio
async def test_usgs_payload_reaches_context_and_filters_before_limit():
    features = [event("outside", lon=30), event("too-old", hours_ago=48),
                event("too-small", mag=1), event("valid"), event("missing-position", lat=None)]
    seen = []
    def handle(req):
        seen.append(str(req.url))
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})
    engine = await mock_fetcher(handle)
    try:
        await engine.fetch_usgs()
        result = await context(request(engine), limit=1)
        assert [q["id"] for q in result["earthquakes"]] == ["valid"]
        assert result["earthquakes"][0]["lat"] == 19.4
        assert result["sources"]["usgs"]["status"] == "available"
        assert result["sources"]["usgs"]["last_success"]
        assert engine.cache["quakes"] == engine.cache["usgs"]
        assert seen == ["https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.geojson"]
        extended = await context(request(engine), earthquake_days=3)
        assert [q["id"] for q in extended["earthquakes"]] == ["too-old", "valid"]
        geojson = await get_geo_earthquakes(min_magnitude=2.5, days=1, limit=10,
                                          req=request(engine), current_user=None, _rate_limit=True)
        assert isinstance(geojson["features"][0]["properties"]["time"], (int, float))
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_usgs_failure_preserves_cache_without_new_success():
    failing = False
    def handle(req):
        return httpx.Response(503) if failing else httpx.Response(200, json={"features": [event("last-good")]})
    engine = await mock_fetcher(handle)
    try:
        await engine.fetch_usgs()
        last_success = engine.last_fetch["usgs"]
        failing = True
        await engine.fetch_usgs()
        result = await context(request(engine))
        assert result["earthquakes"][0]["id"] == "last-good"
        assert result["sources"]["usgs"]["status"] == "stale"
        assert engine.last_fetch["usgs"] == last_success
        assert engine.metrics["fetch_usgs"]["success"] == 1
        assert engine.metrics["fetch_usgs"]["fail"] == 1
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_empty_result_is_success_but_missing_adapter_is_not():
    engine = await mock_fetcher(lambda req: httpx.Response(200, json={"features": []}))
    try:
        await engine.fetch_usgs()
        assert engine.source_status["usgs"]["status"] == "available"
        assert engine.cache["quakes"] == []
        result = await engine.fetch_adsb_lol()
        assert result["error"] == "ValueError"
        assert "adsb_lol" not in engine.cache and "adsb_lol" not in engine.last_fetch
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_opensky_normalization_supplies_fallback_with_explicit_units(monkeypatch):
    monkeypatch.setenv("TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS", "1")
    row = ["abc123", "TEST123 ", "Fixture", 1, datetime.now(timezone.utc).timestamp(),
           -99.1, 19.4, 2000, False, 100, 90, 0]
    engine = await mock_fetcher(lambda req: httpx.Response(200, json={"states": [row]}))
    try:
        await engine.fetch_opensky()
        result = await context(request(engine))
        assert result["aircraft"][0]["hex"] == "abc123"
        assert result["aircraft"][0]["callsign"] == "TEST123"
        assert result["aircraft"][0]["altitude_unit"] == "m"
        assert result["sources"]["opensky"]["status"] == "available"
        assert result["sources"]["adsb_exchange"]["status"] == "unavailable"
    finally:
        await engine.close()


class ProviderResponse:
    def __init__(self, status=200):
        self.status = status
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        return False
    async def json(self):
        return {"ac": [{"hex": "outside", "lat": 60, "lon": 30},
                       {"hex": "abc123", "flight": "TEST123 ", "lat": 19.4, "lon": -99.1,
                        "alt_baro": 10000, "gs": 250, "track": 90, "t": "A320", "seen_pos": 5}]}


class ProviderSession:
    closed = True
    def __init__(self, status=200):
        self.status = status
    def get(self, *_args, **_kwargs):
        return ProviderResponse(self.status)


@pytest.mark.asyncio
async def test_adsb_client_contract_is_consumed_by_both_routes(monkeypatch):
    monkeypatch.setenv("TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS", "1")
    monkeypatch.setenv("ADSBEXCHANGE_API_KEY", "synthetic-fixture")
    adsb = ADSBExchangeClient()
    await adsb.http.close()
    adsb.http = ProviderSession()
    result = await context(request(adsb=adsb))
    assert [a["hex"] for a in result["aircraft"]] == ["abc123"]
    assert result["aircraft"][0]["altitude"] == 10000
    assert result["aircraft"][0]["altitude_unit"] == "ft"
    assert result["sources"]["adsb_exchange"]["status"] == "available"
    age = datetime.now(timezone.utc) - datetime.fromisoformat(result["aircraft"][0]["timestamp"])
    assert 4 <= age.total_seconds() <= 10
    flights = await get_geo_flights(lat_min=19, lat_max=20, lon_min=-100, lon_max=-99, limit=1,
                                   req=request(adsb=adsb), current_user=None, _rate_limit=True)
    assert flights["ac"][0]["hex"] == "abc123" and flights["ac"][0]["spd"] == 250
    adsb.http = ProviderSession(503)
    failed = await context(request(adsb=adsb))
    assert failed["aircraft"] == []
    assert failed["sources"]["adsb_exchange"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_missing_key_disconnected_ais_and_expired_cache_not_available():
    called = False
    async def never_call(*_):
        nonlocal called
        called = True
        raise AssertionError("missing credentials must not call provider")
    engine = await mock_fetcher(lambda req: httpx.Response(200, json={"features": []}))
    try:
        await engine.fetch_usgs()
        engine.last_fetch["usgs"] -= 600
        adsb = SimpleNamespace(api_key="", get_aircraft_in_bbox=never_call)
        ais = SimpleNamespace(connected=False, get_ships_in_bbox=lambda *_: [])
        result = await context(request(engine, adsb, ais))
        assert not called
        assert result["sources"]["adsb_exchange"]["status"] == "disabled_by_default"
        assert result["sources"]["ais"]["status"] == "unavailable"
        assert result["sources"]["usgs"]["status"] == "stale"
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_ais_stale_positions_are_not_live():
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    ais = SimpleNamespace(connected=True, get_ships_in_bbox=lambda *_: [
        {"mmsi": "fixture", "latitude": 19.4, "longitude": -99.1, "timestamp": old}])
    result = await context(request(ais=ais))
    assert result["ships"] == []
    assert result["sources"]["ais"]["status"] == "stale"


def test_inverted_bbox_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _bounds(20, 19, -100, -99)
    assert exc.value.status_code == 422
