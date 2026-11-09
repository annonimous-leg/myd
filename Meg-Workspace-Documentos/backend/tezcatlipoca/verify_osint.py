#!/usr/bin/env python3
"""
verify_osint.py — Verifica que la plataforma OSINT esté correctamente configurada
Ejecutar desde la raíz del proyecto: python verify_osint.py
"""

import asyncio
import httpx
import sys
import json

BASE_URL = "http://localhost:8000"
TIMEOUT = 10

ROUTES = [
    # Core
    ("GET", "/api/telemetry/", "Telemetry"),
    ("GET", "/api/telemetry/cache", "Telemetry Cache"),
    ("GET", "/api/layers/", "Layers"),

    # OSINT
    ("GET", "/api/osint/ip/8.8.8.8", "OSINT IP Lookup"),
    ("GET", "/api/osint/dns/google.com", "OSINT DNS Lookup"),
    ("GET", "/api/osint/cve/CVE-2021-44228", "OSINT CVE Lookup"),

    # Aviation
    ("GET", "/api/aviation/adsb/aircraft", "Aviation ADS-B"),
    ("GET", "/api/aviation/metar/KJFK", "Aviation METAR"),
    ("GET", "/api/aviation/notams?icao=KJFK", "Aviation NOTAMs"),

    # Cyber
    ("GET", "/api/cyber/shodan/search?query=apache", "Shodan Search"),
    ("GET", "/api/cyber/cisa-kev", "CISA KEV"),
    ("GET", "/api/cyber/malware/feodo", "Feodo Tracker"),
    ("GET", "/api/cyber/malware/urlhaus", "URLhaus"),

    # Malware
    ("GET", "/api/malware/", "Malware Feeds"),
    ("GET", "/api/malware/cyber-threats", "Cyber Threats"),

    # Mesh
    ("GET", "/api/mesh/status", "Mesh Status"),
    ("GET", "/api/mesh_governance/nodes", "Mesh Nodes"),
    ("GET", "/api/mesh_governance/proposals", "Mesh Proposals"),

    # Honeypot
    ("GET", "/api/honeypot/status", "Honeypot Status"),

    # Transport
    ("GET", "/api/transport/trains/stations", "Train Stations"),
    ("GET", "/api/transport/gtfs/feeds", "GTFS Feeds"),

    # SAR
    ("GET", "/api/sar/nasa/collections", "NASA Collections"),
    ("GET", "/api/sar/gee/collection", "GEE Collection"),

    # SCM
    ("GET", "/api/scm/vendors", "SCM Vendors"),
    ("GET", "/api/scm/risks", "SCM Risks"),

    # Snapshots
    ("GET", "/api/snapshots/", "Snapshots"),

    # Settings
    ("GET", "/api/settings/", "Settings"),

    # Wormhole
    ("GET", "/api/wormhole/health", "Wormhole Health"),
    ("GET", "/api/wormhole/tunnels", "Wormhole Tunnels"),

    # AI
    ("GET", "/api/ai/tools", "AI Tools"),
]

async def test_route(client: httpx.AsyncClient, method: str, path: str, name: str):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = await client.get(url, timeout=TIMEOUT)
        elif method == "POST":
            resp = await client.post(url, json={}, timeout=TIMEOUT)
        else:
            return "SKIP", name, path, "Unknown method"

        status = resp.status_code
        if status == 200:
            return "OK", name, path, f"{status}"
        elif status == 404:
            return "FAIL", name, path, f"{status} NOT FOUND"
        elif status == 422:
            return "WARN", name, path, f"{status} VALIDATION"
        elif status == 503:
            return "WARN", name, path, f"{status} SERVICE UNAVAILABLE (API key?)"
        else:
            return "WARN", name, path, f"{status}"
    except httpx.ConnectError:
        return "FAIL", name, path, "Connection refused"
    except Exception as e:
        return "FAIL", name, path, str(e)[:50]

async def main():
    print("=" * 70)
    print("🔍 TU-OSINT-PLATFORM — VERIFICACIÓN DE RUTAS")
    print(f"   Backend: {BASE_URL}")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[
            test_route(client, method, path, name)
            for method, path, name in ROUTES
        ])

    ok = warn = fail = 0

    for status, name, path, detail in results:
        icon = {"OK": "✅", "WARN": "🟡", "FAIL": "❌", "SKIP": "⏭️"}.get(status, "❓")
        print(f"  {icon} {status:4s} {name:25s} {path:40s} {detail}")
        if status == "OK": ok += 1
        elif status == "WARN": warn += 1
        elif status == "FAIL": fail += 1

    print()
    print(f"📊 Resultados: {ok} OK | {warn} WARN | {fail} FAIL | {len(results)} total")

    if fail > 0:
        print("\n❌ Hay rutas que fallan. Asegúrate de que el backend esté corriendo:")
        print("   python main.py")
        sys.exit(1)
    elif warn > 0:
        print("\n🟡 Algunas rutas necesitan configuración (API keys, parámetros).")
        print("   Revisa tu archivo .env para las API keys de Shodan, Censys, etc.")
    else:
        print("\n✅ Todas las rutas responden correctamente.")

if __name__ == "__main__":
    asyncio.run(main())
