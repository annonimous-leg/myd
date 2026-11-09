"""Contact public providers and exercise the application's real normalization path.

This is live integration evidence from an isolated runner, not a deployment,
a surveyed terrain, licensed Street View imagery, or SAT acceptance.
"""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tezcatlipoca"))
from services.data_fetcher import DataFetcherEngine
from routers.geo import get_geo_context


async def main():
    report = {
        "scope": "isolated_runner_live_public_providers",
        "commit": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "responses": [], "checks": [], "production_deployment": False,
    }
    engine = DataFetcherEngine()

    async def record(response):
        body = await response.aread()
        report["responses"].append({
            "url": str(response.request.url), "status": response.status_code,
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "provider_date": response.headers.get("date"),
            "last_modified": response.headers.get("last-modified"),
        })

    engine.http.event_hooks["response"] = [record]
    failed = False
    try:
        await engine.fetch_usgs()
        if engine.source_status["usgs"]["status"] != "available":
            raise RuntimeError("USGS request or normalization failed")
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(data_fetcher=engine, adsb_exchange=None, ais_connector=None)),
            state=SimpleNamespace(tenant_id=None, megalodon_user_id=None),
        )
        context = await get_geo_context(
            lat_min=-90, lat_max=90, lon_min=-180, lon_max=180, earthquake_days=1,
            earthquake_magnitude=0, limit=100, req=request, current_user=None, _rate_limit=True,
        )
        if not context["earthquakes"]:
            raise RuntimeError("No recent USGS observations reached geographic context")
        report["checks"].append({
            "provider": "USGS", "result": "passed",
            "normalized_records": len(engine.cache["quakes"]),
            "context_records_last_day": len(context["earthquakes"]),
            "provenance": context["sources"]["usgs"],
            "latest_observation": max(q["timestamp"] for q in engine.cache["quakes"]),
        })
        await engine.fetch_nws()
        if engine.source_status["nws"]["status"] != "available":
            raise RuntimeError("Open-Meteo request failed")
        weather = (await engine.get_live_batch())["weather"]
        current = weather.get("current", {})
        if not all(key in current for key in ("time", "temperature_2m", "wind_speed_10m")):
            raise RuntimeError("Weather normalization did not reach live batch")
        observed = datetime.fromisoformat(current["time"]).replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if not -3600 <= age <= 10800:
            raise RuntimeError("Weather provider observation is outside the freshness window")
        report["checks"].append({
            "provider": "Open-Meteo", "result": "passed",
            "scope": "configured Mexico City reference point, not site-specific weather",
            "observation_time": current["time"], "age_seconds": age,
            "coordinates": [weather["latitude"], weather["longitude"]],
            "units": weather.get("current_units", {}),
        })
    except Exception as exc:
        failed = True
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        await engine.close()
        report["result"] = "failed" if failed else "passed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        Path("live-provider-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
