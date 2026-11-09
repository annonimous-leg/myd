from services.secure_requests import sync_get, async_get
"""OSINT Recon Engine - Implementación real con APIs públicas."""
import os
import json
import socket
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import aiohttp

from core.observability import build_logger

logger = build_logger("tu_osint.osint_engine")


class OSINTReconEngine:
    """Motor de reconocimiento OSINT con fuentes reales."""

    def __init__(self):
        self.http = aiohttp.ClientSession()
        self.cache: Dict[str, Any] = {}
        self.ipinfo_token = os.getenv("IPINFO_TOKEN", "")

    async def close(self):
        if self.http and not self.http.closed:
            await self.http.close()

    async def lookup_ip(self, ip: str) -> Dict[str, Any]:
        """Lookup IP usando IPinfo API (gratuita)."""
        cache_key = f"ip:{ip}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # IPinfo Lite API - gratuita, sin token requerido para básico
            url = f"https://api.ipinfo.io/lite/{ip}"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = {
                        "ip": ip,
                        "country": data.get("country", "Unknown"),
                        "country_code": data.get("country_code", ""),
                        "asn": data.get("asn", ""),
                        "as_name": data.get("as_name", ""),
                        "source": "ipinfo.io",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    self.cache[cache_key] = result
                    return result
        except Exception as e:
            logger.debug(f"lookup_ip({ip}): ipinfo.io falló, se cae a fallback: {e}")

        # Fallback: whois básico
        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except Exception as e:
            logger.debug(f"lookup_ip({ip}): resolución reversa falló: {e}")
            hostname = None

        return {
            "ip": ip,
            "country": "Unknown",
            "hostname": hostname,
            "source": "fallback",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def lookup_dns(self, domain: str) -> Dict[str, Any]:
        """Lookup DNS básico."""
        import dns.resolver
        records = {}
        for rtype in ["A", "AAAA", "MX", "NS", "TXT"]:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                records[rtype] = [str(r) for r in answers]
            except Exception as e:
                # NXDOMAIN/NoAnswer por tipo es normal (no todo dominio
                # tiene AAAA o TXT); se loguea en debug nada más para no
                # perder señal si en cambio es un fallo real de resolver.
                logger.debug(f"lookup_dns({domain}): sin registros {rtype}: {e}")
        return {
            "domain": domain,
            "records": records,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def lookup_whois(self, domain: str) -> Dict[str, Any]:
        """WHOIS básico vía whois API pública."""
        try:
            url = f"https://rdap.org/domain/{domain}"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "domain": domain,
                        "registrar": data.get("entities", [{}])[0].get("handle", "Unknown"),
                        "created": data.get("events", [{}])[0].get("eventDate", ""),
                        "source": "rdap.org",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            logger.debug(f"lookup_whois({domain}): rdap.org falló: {e}")
        return {"domain": domain, "source": "unavailable"}

    async def lookup_cve(self, cve_id: str) -> Dict[str, Any]:
        """Lookup CVE vía NVD API."""
        try:
            url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={cve_id}"
            async with self.http.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vulns = data.get("vulnerabilities", [])
                    if vulns:
                        cve = vulns[0].get("cve", {})
                        return {
                            "cve_id": cve_id,
                            "description": cve.get("descriptions", [{}])[0].get("value", ""),
                            "severity": cve.get("metrics", {}).get("cvssMetricV31", [{}])[0].get("cvssData", {}).get("baseSeverity", "Unknown"),
                            "source": "nvd.nist.gov",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
        except Exception as e:
            logger.debug(f"lookup_cve({cve_id}): nvd.nist.gov falló: {e}")
        return {"cve_id": cve_id, "source": "unavailable"}


    async def lookup(self, target: str, lookup_type: str = "auto") -> Dict[str, Any]:
        """Wrapper unificado para lookups. Detecta tipo automáticamente."""
        if lookup_type == "auto":
            if ":" in target or target.replace(".", "").replace("-", "").isdigit():
                lookup_type = "ip"
            elif "." in target:
                lookup_type = "dns"
            elif target.startswith("CVE-"):
                lookup_type = "cve"
            else:
                lookup_type = "unknown"

        if lookup_type == "ip":
            return await self.lookup_ip(target)
        elif lookup_type == "dns":
            return await self.lookup_dns(target)
        elif lookup_type == "whois":
            return await self.lookup_whois(target)
        elif lookup_type == "cve":
            return await self.lookup_cve(target)
        else:
            return {"entity": target, "type": lookup_type, "error": "Unknown lookup type"}

    async def expand_entity(self, entity: str, depth: int = 1) -> Dict[str, Any]:
        """Expandir entidad con lookups básicos."""
        result = {"entity": entity, "depth": depth, "connections": []}

        # Detectar tipo de entidad
        if ":" in entity:  # IP
            ip_data = await self.lookup_ip(entity)
            result["connections"].append({"type": "ip", "data": ip_data})
        elif "." in entity:  # Dominio
            dns_data = await self.lookup_dns(entity)
            result["connections"].append({"type": "dns", "data": dns_data})
            whois_data = await self.lookup_whois(entity)
            result["connections"].append({"type": "whois", "data": whois_data})
        elif entity.startswith("CVE-"):  # CVE
            cve_data = await self.lookup_cve(entity)
            result["connections"].append({"type": "cve", "data": cve_data})

        return result
