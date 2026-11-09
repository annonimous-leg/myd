#!/usr/bin/env python3
"""Megalodon + Tezcatlipoca: arquitectura, dependencias y dimensionamiento VPS.

El archivo documenta el árbol auditado y calcula estimaciones de almacenamiento
para cotización. No instala nada y no sustituye un benchmark de carga.
"""
from __future__ import annotations
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend/app"

DEPENDENCIES = {
    "core_api": ["fastapi", "uvicorn", "pydantic", "pydantic-settings", "sqlalchemy", "alembic"],
    "database": ["asyncpg", "psycopg2-binary", "geoalchemy2", "PostGIS"],
    "async": ["redis", "celery", "apscheduler"],
    "bim": ["ifcopenshell", "numpy", "scipy", "shapely"],
    "gis": ["geopandas", "pyproj", "shapely", "geojson"],
    "documents": ["pytesseract", "opencv-python", "Pillow", "pdf2image", "reportlab"],
    "security": ["bcrypt", "PyJWT", "cryptography", "PyNaCl"],
    "integrations": ["httpx", "aiohttp", "supabase", "twilio", "earthengine-api"],
    "observability": ["OpenTelemetry", "Prometheus/Grafana/Loki/Jaeger at infrastructure level"],
    "frontend": ["React 19", "TypeScript", "Vite", "Three.js", "React Three Fiber", "Zustand", "Recharts"],
}

PROFILE = {
    "dev": {"vcpu": 4, "ram_gb": 8, "nvme_gb": 120, "workers": 2},
    "production_start": {"vcpu": 8, "ram_gb": 32, "nvme_gb": 250, "workers": 4},
    "bim_gis_heavy": {"vcpu": 16, "ram_gb": 64, "nvme_gb": 500, "workers": 8},
    "large_scale_target": {
        "api": "8-16 vCPU / 32-64 GB RAM",
        "workers": "separate 8-32 vCPU pool depending on IFC/OCR/GIS batch volume",
        "database": "dedicated PostgreSQL/PostGIS node with SSD/NVMe + HA/replication",
        "redis": "dedicated Redis/HA or managed service",
        "storage": "object storage for IFC/PDF/raster/video; DB only for metadata",
    },
}


def source_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and '.git' not in p.parts and 'node_modules' not in p.parts and '.venv' not in p.parts)


def count(pattern: str, root: Path) -> int:
    return sum(1 for _ in root.rglob(pattern)) if root.exists() else 0


def architecture():
    return {
        "experience": "React/Tauri/Electron-capable shell -> Megalodon client -> FastAPI",
        "core": "auth + tenant + entitlements + audit + workflows + domain services",
        "engineering": "BIM 2D/3D/4D/5D + topography + CostOS + planning + documents",
        "tezcatlipoca": "Geo/OSINT/Cyber/SAR/Aviation/Transport/Telemetry/Photogrammetry",
        "bridge": "Megalodon token/cookie -> Tezcatlipoca bridge -> shadow user/audit context -> tenant",
        "topography_flow": [
            "GNSS/CSV/field data",
            "Tezcatlipoca contextual geospatial sources",
            "authenticated bridge",
            "Megalodon geodesy/TIN/volume engine",
            "BIM/CostOS/Planning",
            "audit + expediente",
        ],
    }


def main():
    print(json.dumps({
        "source_size_mb": round(source_size(ROOT) / 1024 / 1024, 2),
        "backend_py": count('*.py', BACKEND),
        "frontend_ts_tsx": count('*.ts', FRONTEND) + count('*.tsx', FRONTEND),
        "dependencies": DEPENDENCIES,
        "profiles": PROFILE,
        "architecture": architecture(),
        "note": "La capacidad real de carga debe validarse con pruebas de concurrencia y datasets IFC/GIS representativos.",
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
