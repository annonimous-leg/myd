"""Deterministic synthetic GRIB-edition contracts. No live ECMWF data is bundled."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import numpy as np

from services.weather.ecmwf_grids import ECMWFGridStore


def fixture_grid(root, *, run_hours_ago=3, mismatch_sha=False):
    run = datetime.now(timezone.utc) - timedelta(hours=run_hours_ago)
    version = run.strftime("%Y%m%d%H") + "-006"
    directory = root / "versions" / version
    directory.mkdir(parents=True)
    arrays = {
        "2t": np.array([[280, 285, 290, 295], [282, 287, 292, 297], [284, 289, 294, 299]], dtype="<f4"),
        "10u": np.full((3, 4), 3.0, dtype="<f4"),
        "10v": np.full((3, 4), 4.0, dtype="<f4"),
    }
    fields = {}
    for name, arr in arrays.items():
        filename = directory / f"{name}.npy"
        np.save(filename, arr)
        fields[name] = {"filename": filename.name, "sha256": hashlib.sha256(filename.read_bytes()).hexdigest()}
    if mismatch_sha:
        fields["2t"]["sha256"] = "0" * 64
    manifest = {
        "version": version, "provider": "ECMWF IFS Open Data", "license": "CC-BY-4.0",
        "run_time": run.isoformat(), "valid_time": (run + timedelta(hours=6)).isoformat(),
        "forecast_step_hours": 6, "fields": fields, "source_grib_sha256": "f" * 64,
        "grid": {
            "ni": 4, "nj": 3, "first_lat": 90.0, "first_lon": 0.0,
            "lat_step": -1.0, "lon_step": 90.0,
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "active.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    return version


def test_global_forecast_samples_real_cells_and_converts_units(tmp_path):
    fixture_grid(tmp_path)
    store = ECMWFGridStore(root=tmp_path)
    p = store.forecast_at(lat=89.0, lon=-90.0)
    assert p["status"] == "available"
    assert p["temperature_2m_c"] == round(297 - 273.15, 2)
    assert p["wind_10m_ms"] == 5
    assert p["grid_point"] == {"lat": 89.0, "lon": -90.0}
    assert p["attribution"] == "ECMWF Open Data (IFS)"
    assert p["status_detail"] == "nearest_grid_point_forecast_not_site_observation"


def test_no_global_data_reports_configuration_not_fake_values(monkeypatch):
    monkeypatch.delenv("TEZCATLIPOCA_ECMWF_STORE", raising=False)
    assert ECMWFGridStore().forecast_at(19.4, -99.1)["status"] == "config_required"


def test_invalid_grid_checksums_are_rejected(tmp_path):
    fixture_grid(tmp_path, mismatch_sha=True)
    assert ECMWFGridStore(root=tmp_path).forecast_at(89, 90)["status"] == "unavailable"


def test_expired_run_is_stale_and_does_not_return_weather_values(tmp_path):
    fixture_grid(tmp_path, run_hours_ago=48)
    result = ECMWFGridStore(root=tmp_path).forecast_at(89, 0)
    assert result["status"] == "stale"
    assert "temperature_2m_c" not in result


def test_coordinates_and_version_pointer_are_validated(tmp_path):
    fixture_grid(tmp_path)
    store = ECMWFGridStore(root=tmp_path)
    assert store.forecast_at(91, 0)["status"] == "invalid_coordinates"
    assert store.forecast_at(float("nan"), 0)["status"] == "invalid_coordinates"
    (tmp_path / "active.json").write_text('{"version":"../../etc/passwd"}')
    assert ECMWFGridStore(root=tmp_path).forecast_at(89, 0)["status"] == "unavailable"


def test_unsupported_coverage_is_not_extrapolated(tmp_path):
    fixture_grid(tmp_path)
    # Synthetic grid is only 88-90 N; 19 degrees N must be unavailable.
    r = ECMWFGridStore(root=tmp_path).forecast_at(19.4, -99.1)
    assert r["status"] == "out_of_coverage"
