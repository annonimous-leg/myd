"""Read locally ingested ECMWF IFS Open Data GRIB fields (CC BY 4.0).

No hosted weather API, synthetic forecasts, or external requests are involved
in this service. A separate operator job publishes GRIB-derived NumPy grids.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


_VERSION_RE = re.compile(r"^\d{10}-\d{3}$")
_FIELDS = ("2t", "10u", "10v")
_LATEST_RUN_HOURS = 36


class ECMWFGridStore:
    def __init__(self, root: Path | str | None = None):
        configured = root if root is not None else os.getenv("TEZCATLIPOCA_ECMWF_STORE", "").strip()
        self.root = Path(configured).resolve() if configured else None
        self._cache_version: str | None = None
        self._cache: tuple[dict, dict[str, np.ndarray]] | None = None

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Missing UTC offset")
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fp:
            for part in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(part)
        return digest.hexdigest()

    def _load(self):
        if self.root is None:
            raise FileNotFoundError("No ECMWF data store configured")
        active = json.loads((self.root / "active.json").read_text(encoding="utf-8"))
        version = active.get("version")
        if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
            raise ValueError("Invalid ECMWF version pointer")
        if self._cache_version == version and self._cache is not None:
            return self._cache
        root = self.root / "versions" / version
        metadata = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if metadata.get("version") != version or metadata.get("provider") != "ECMWF IFS Open Data":
            raise ValueError("Invalid ECMWF manifest")
        if metadata.get("license") != "CC-BY-4.0":
            raise ValueError("ECMWF license metadata missing")
        grid = metadata["grid"]
        ni, nj = grid["ni"], grid["nj"]
        if (not isinstance(ni, int) or not isinstance(nj, int) or
                not 1 <= ni <= 5000 or not 1 <= nj <= 3000 or ni * nj > 10_000_000):
            raise ValueError("Unsupported forecast grid shape")
        arrays = {}
        for param in _FIELDS:
            descriptor = metadata["fields"][param]
            if descriptor["filename"] != param + ".npy":
                raise ValueError("Unexpected ECMWF grid filename")
            filename = root / (param + ".npy")
            if self._sha256(filename) != descriptor["sha256"]:
                raise ValueError("ECMWF grid checksum mismatch")
            array = np.load(filename, mmap_mode="r", allow_pickle=False)
            if array.shape != (nj, ni) or array.dtype != np.dtype("<f4"):
                raise ValueError("ECMWF grid shape or dtype mismatch")
            arrays[param] = array
        self._cache = (metadata, arrays)
        self._cache_version = version
        return self._cache

    def forecast_at(self, lat: float, lon: float) -> dict:
        if (not isinstance(lat, (float, int)) or not isinstance(lon, (float, int))
                or isinstance(lat, bool) or isinstance(lon, bool) or
                not math.isfinite(lat) or not math.isfinite(lon) or
                not -90 <= lat <= 90 or not -180 <= lon <= 180):
            return {"status": "invalid_coordinates", "source": "ecmwf_open_data"}
        if self.root is None:
            return {"status": "config_required", "source": "ecmwf_open_data",
                    "reason": "Set TEZCATLIPOCA_ECMWF_STORE after ingesting real GRIB fields"}
        try:
            meta, arrays = self._load()
            grid = meta["grid"]
            ni, nj = grid["ni"], grid["nj"]
            dy, dx = grid["lat_step"], grid["lon_step"]
            if (not isinstance(dy, (float, int)) or not isinstance(dx, (float, int))
                    or abs(dy) < 1e-9 or dx <= 0):
                raise ValueError("Invalid grid increments")
            row = round((lat - grid["first_lat"]) / dy)
            # ECMWF global 0..360 longitudes; wrap negative user longitudes.
            longitude = lon % 360
            col = round(((longitude - grid["first_lon"]) % 360) / dx)
            if not 0 <= row < nj or not 0 <= col < ni:
                return {"status": "out_of_coverage", "source": "ecmwf_open_data"}
            sampled = {key: float(array[row, col]) for key, array in arrays.items()}
            if not all(math.isfinite(v) for v in sampled.values()):
                return {"status": "no_data", "source": "ecmwf_open_data"}
            run = self._parse_utc(meta["run_time"])
            valid = self._parse_utc(meta["valid_time"])
            age_hours = (datetime.now(timezone.utc) - run).total_seconds() / 3600
            if age_hours < -1 or age_hours > _LATEST_RUN_HOURS:
                return {"status": "stale", "source": "ecmwf_open_data",
                        "run_time": meta["run_time"], "valid_time": meta["valid_time"],
                        "reason": "Forecast run outside freshness window"}
            temperature_c = round(sampled["2t"] - 273.15, 2)
            wind_speed = round(math.hypot(sampled["10u"], sampled["10v"]), 2)
            return {
                "status": "available", "source": "ecmwf_open_data",
                "model": "IFS", "resolution_degrees": abs(dx),
                "license": "CC-BY-4.0", "attribution": "ECMWF Open Data (IFS)",
                "run_time": meta["run_time"], "valid_time": meta["valid_time"],
                "forecast_step_hours": meta["forecast_step_hours"],
                "query": {"lat": lat, "lon": lon},
                "grid_point": {
                    "lat": round(grid["first_lat"] + row * dy, 6),
                    "lon": round((grid["first_lon"] + col * dx + 180) % 360 - 180, 6),
                },
                "temperature_2m_c": temperature_c,
                "wind_10m_ms": wind_speed,
                "wind_u_10m_ms": round(sampled["10u"], 2),
                "wind_v_10m_ms": round(sampled["10v"], 2),
                "status_detail": "nearest_grid_point_forecast_not_site_observation",
                "dataset_sha256": meta.get("source_grib_sha256"),
            }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return {"status": "unavailable", "source": "ecmwf_open_data",
                    "reason": "Data missing, invalid or failed integrity validation"}
