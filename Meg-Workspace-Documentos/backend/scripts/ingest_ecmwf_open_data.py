"""Offline GRIB2 -> immutable ECMWF IFS grid edition for Tezcatlipoca.

Operator workflow (no unlicensed hosted API):
  pip install eccodes ecmwf-opendata
  python -c "from ecmwf.opendata import Client; Client(source='ecmwf',model='ifs',resol='0p25').retrieve(type='fc',step=24,param=['2t','10u','10v'],target='ifs.grib2')"
  python scripts/ingest_ecmwf_open_data.py --grib ifs.grib2 --store ./data/ecmwf

This command never invents forecast values, downloads data, or sends data to
third parties. Only regular grids with verified common metadata are accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PARAMS = ("2t", "10u", "10v")
MAX_INPUT_BYTES = 180_000_000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_grib(path: Path):
    try:
        from eccodes import codes_get, codes_get_values, codes_grib_new_from_file, codes_release
    except ImportError as exc:
        raise RuntimeError("Install optional ecCodes: pip install eccodes") from exc

    fields = {}
    shared = None
    with path.open("rb") as file:
        while True:
            handle = codes_grib_new_from_file(file)
            if handle is None:
                break
            try:
                param = str(codes_get(handle, "shortName"))
                if param not in PARAMS:
                    continue
                if param in fields:
                    raise ValueError(f"Duplicate field {param}; one forecast step per file is required")
                ni, nj = int(codes_get(handle, "Ni")), int(codes_get(handle, "Nj"))
                if ni * nj > 10_000_000 or ni < 100 or nj < 100:
                    raise ValueError("Expected a regular global forecast grid")
                if int(codes_get(handle, "jPointsAreConsecutive")) != 0:
                    raise ValueError("Unsupported GRIB scanning order")
                if int(codes_get(handle, "iScansNegatively")) != 0:
                    raise ValueError("Unsupported negative longitude scanning")
                lat_step = float(codes_get(handle, "jDirectionIncrementInDegrees"))
                if int(codes_get(handle, "jScansPositively")) == 0:
                    lat_step = -lat_step
                metadata = {
                    "grid": {
                        "ni": ni, "nj": nj,
                        "first_lat": float(codes_get(handle, "latitudeOfFirstGridPointInDegrees")),
                        "first_lon": float(codes_get(handle, "longitudeOfFirstGridPointInDegrees")),
                        "lat_step": lat_step,
                        "lon_step": float(codes_get(handle, "iDirectionIncrementInDegrees")),
                    },
                    "run_time": str(codes_get(handle, "dataDate")) + f"{int(codes_get(handle, 'dataTime')):04d}",
                    "valid_time": str(codes_get(handle, "validityDate")) + f"{int(codes_get(handle, 'validityTime')):04d}",
                    "forecast_step_hours": int(codes_get(handle, "endStep")),
                }
                # The data must actually cover most of the world. A regional
                # subset cannot masquerade as globally queryable ECMWF data.
                g = metadata["grid"]
                if (g["lon_step"] <= 0 or not 0.09 <= abs(g["lat_step"]) <= 0.26
                        or abs(ni * g["lon_step"] - 360) > g["lon_step"] * 2
                        or abs((nj - 1) * g["lat_step"]) < 175):
                    raise ValueError("Unsupported ECMWF grid or incomplete global coverage")
                if shared is not None and metadata != shared:
                    raise ValueError("Mismatched run, grid or lead time across fields")
                shared = metadata
                data = np.asarray(codes_get_values(handle), dtype="<f4")
                if data.size != ni * nj:
                    raise ValueError("Invalid GRIB field length")
                fields[param] = data.reshape(nj, ni)
            finally:
                codes_release(handle)
    if shared is None or set(fields) != set(PARAMS):
        raise ValueError(f"GRIB file must contain exactly these surface parameters: {PARAMS}")
    return shared, fields


def _iso(value: str) -> str:
    date = datetime.strptime(value, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    return date.isoformat().replace("+00:00", "Z")


def publish(grib: Path, store: Path) -> dict:
    grib = grib.resolve()
    if not grib.is_file() or not 0 < grib.stat().st_size <= MAX_INPUT_BYTES:
        raise ValueError("Source GRIB is absent or larger than the bounded ingest limit")
    meta, fields = read_grib(grib)
    run, valid = _iso(meta["run_time"]), _iso(meta["valid_time"])
    step = meta["forecast_step_hours"]
    if step < 0 or step > 240 or step % 3 != 0:
        raise ValueError("Unsupported IFS forecast lead time")
    version = meta["run_time"][:10] + f"-{step:03d}"
    store.mkdir(parents=True, exist_ok=True)
    versions = store / "versions"
    versions.mkdir(exist_ok=True)
    final_dir = versions / version
    if final_dir.exists():
        raise FileExistsError(f"Version {version} already published; immutable editions cannot be overwritten")
    staged = Path(tempfile.mkdtemp(prefix=".staging-", dir=versions))
    try:
        metadata = {
            "version": version, "provider": "ECMWF IFS Open Data", "model": "IFS",
            "license": "CC-BY-4.0", "attribution": "ECMWF Open Data (IFS)",
            "run_time": run, "valid_time": valid, "forecast_step_hours": step,
            "source_grib_sha256": sha256_file(grib), "source_grib_bytes": grib.stat().st_size,
            "grid": meta["grid"], "fields": {},
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "data_origin": "operator_supplied_real_grib_not_live_observation",
        }
        for param in PARAMS:
            target = staged / f"{param}.npy"
            np.save(target, fields[param], allow_pickle=False)
            metadata["fields"][param] = {"filename": f"{param}.npy", "sha256": sha256_file(target), "unit": "K" if param == "2t" else "m/s"}
        (staged / "manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        staged.rename(final_dir)
        pointer = store / "active.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=store, prefix=".active-", suffix=".json", delete=False) as temporary:
            json.dump({"version": version}, temporary)
            tmp_name = temporary.name
        os.replace(tmp_name, pointer)
        return {"status": "published", "version": version, "run_time": run, "valid_time": valid, "fields": list(PARAMS)}
    finally:
        if staged.exists():
            shutil.rmtree(staged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grib", type=Path, required=True, help="Locally downloaded ECMWF IFS GRIB2 file")
    parser.add_argument("--store", type=Path, required=True, help="Tezcatlipoca managed forecast dataset root")
    args = parser.parse_args()
    print(json.dumps(publish(args.grib, args.store), indent=2))


if __name__ == "__main__":
    main()
