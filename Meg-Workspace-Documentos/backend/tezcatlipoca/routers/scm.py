"""SCM Router — Supply Chain Risk Management con inteligencia real.

Fuentes: CISA KEV, Shodan, Feodo Tracker, GreyNoise.
Fórmula de risk score ponderada industrial.
Caching TTL 5 minutos.
"""
from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
import structlog

from core.rate_limit import rate_limit_standard, rate_limit_strict
from db.models import User
from routers.auth import get_current_user, require_role

logger = structlog.get_logger("scm")
router = APIRouter(tags=["supply-chain"])


class VendorProfile(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern=r"^(software|security|infrastructure|cloud|hardware|devops|networking|iot|other)$")
    products: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    risk_score: float = Field(..., ge=0.0, le=10.0)
    cve_count: int = Field(default=0, ge=0)
    critical_cves: int = Field(default=0, ge=0)
    kev_count: int = Field(default=0, ge=0)
    shodan_exposed_hosts: int = Field(default=0, ge=0)
    shodan_services: List[str] = Field(default_factory=list)
    feodo_ips: int = Field(default=0, ge=0)
    greynoise_noise: bool = Field(default=False)
    dependencies: int = Field(default=0, ge=0)
    third_parties: int = Field(default=0, ge=0)
    data_quality: str = Field(default="partial", pattern=r"^(complete|partial|degraded)$")
    sources: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    vendor_id: str
    overall_risk: float = Field(..., ge=0.0, le=10.0)
    recommendations: List[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


VENDOR_REGISTRY: Dict[str, Dict[str, Any]] = {
    "microsoft": {"name": "Microsoft", "category": "software", "products": ["Windows", "Office 365", "Azure", "Exchange", "SQL Server"], "domains": ["microsoft.com", "azure.com", "office.com"]},
    "crowdstrike": {"name": "CrowdStrike", "category": "security", "products": ["Falcon", "Falcon OverWatch", "Falcon Intelligence"], "domains": ["crowdstrike.com"]},
    "solarwinds": {"name": "SolarWinds", "category": "infrastructure", "products": ["Orion", "SAM", "NPM"], "domains": ["solarwinds.com"]},
    "kaseya": {"name": "Kaseya", "category": "it-management", "products": ["VSA", "BMS", "IT Glue"], "domains": ["kaseya.com"]},
    "codecov": {"name": "Codecov", "category": "devops", "products": ["Code Coverage"], "domains": ["codecov.io"]},
    "paloalto": {"name": "Palo Alto Networks", "category": "security", "products": ["PAN-OS", "Prisma", "Cortex"], "domains": ["paloaltonetworks.com"]},
    "fortinet": {"name": "Fortinet", "category": "security", "products": ["FortiGate", "FortiSIEM", "FortiEDR"], "domains": ["fortinet.com"]},
    "cisco": {"name": "Cisco", "category": "networking", "products": ["IOS", "Webex", "Umbrella", "SecureX"], "domains": ["cisco.com"]},
    "vmware": {"name": "VMware", "category": "infrastructure", "products": ["vSphere", "NSX", "vSAN", "Workspace ONE"], "domains": ["vmware.com"]},
    "atlassian": {"name": "Atlassian", "category": "devops", "products": ["Jira", "Confluence", "Bitbucket"], "domains": ["atlassian.com"]},
}


@dataclass
class CacheEntry:
    data: Any
    expires_at: datetime

_cache: Dict[str, CacheEntry] = {}
CACHE_TTL = 300


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and entry.expires_at > datetime.now(timezone.utc):
        return entry.data
    if entry:
        del _cache[key]
    return None


def _cache_set(key: str, data: Any, ttl: int = CACHE_TTL) -> None:
    _cache[key] = CacheEntry(data=data, expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl))


async def _fetch_cisa_kev(vendor_name: str) -> Dict[str, Any]:
    cache_key = f"cisa_kev:{vendor_name.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from services.malware.cisa_kev import CISAKEVClient
        client = CISAKEVClient()
        catalog = client.fetch(use_cache=True)
        vendor_cves = [v for v in catalog if vendor_name.lower() in v.get("vendor", "").lower() or vendor_name.lower() in v.get("product", "").lower()]
        result = {"count": len(vendor_cves), "cves": vendor_cves[:20], "known_ransomware": sum(1 for v in vendor_cves if v.get("known_ransomware")), "source": "cisa_kev"}
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.warning("scm_cisa_kev_failed", vendor=vendor_name, error=str(exc))
        return {"count": 0, "cves": [], "known_ransomware": 0, "source": "cisa_kev", "error": str(exc)}


async def _fetch_shodan(vendor_name: str) -> Dict[str, Any]:
    cache_key = f"shodan:{vendor_name.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from services.malware.shodan_connector import ShodanConnector
        connector = ShodanConnector()
        if not connector.api_key:
            return {"hosts": 0, "services": [], "source": "shodan", "error": "no_api_key"}
        data = connector._get("/shodan/host/search", {"query": f'org:"{vendor_name}"', "facets": "port"})
        matches = data.get("matches", [])
        services = list(set(str(m.get("port", "")) for m in matches if m.get("port")))
        result = {"hosts": data.get("total", 0), "services": services[:20], "source": "shodan"}
        _cache_set(cache_key, result, ttl=600)
        return result
    except Exception as exc:
        logger.warning("scm_shodan_failed", vendor=vendor_name, error=str(exc))
        return {"hosts": 0, "services": [], "source": "shodan", "error": str(exc)}


async def _fetch_feodo(vendor_domains: List[str]) -> Dict[str, Any]:
    cache_key = f"feodo:{','.join(sorted(vendor_domains))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from services.malware.feodo_tracker import FeodoTrackerClient
        client = FeodoTrackerClient()
        malicious_ips = set()
        for domain in vendor_domains:
            try:
                ips = socket.gethostbyname_ex(domain)[2]
                for ip in ips:
                    if await client.check_ip(ip):
                        malicious_ips.add(ip)
            except Exception:
                continue
        result = {"malicious_ips": list(malicious_ips), "count": len(malicious_ips), "source": "feodo_tracker"}
        _cache_set(cache_key, result, ttl=600)
        return result
    except Exception as exc:
        logger.warning("scm_feodo_failed", domains=vendor_domains, error=str(exc))
        return {"malicious_ips": [], "count": 0, "source": "feodo_tracker", "error": str(exc)}


async def _fetch_greynoise(vendor_domains: List[str]) -> Dict[str, Any]:
    cache_key = f"greynoise:{','.join(sorted(vendor_domains))}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        from services.malware.grey_noise import GreyNoiseClient
        client = GreyNoiseClient()
        noise_ips = 0
        for domain in vendor_domains:
            try:
                ips = socket.gethostbyname_ex(domain)[2]
                for ip in ips:
                    context = client.ip_context(ip)
                    if context.get("noise", False):
                        noise_ips += 1
            except Exception:
                continue
        result = {"noise_ips": noise_ips, "source": "greynoise"}
        _cache_set(cache_key, result, ttl=600)
        return result
    except Exception as exc:
        logger.warning("scm_greynoise_failed", domains=vendor_domains, error=str(exc))
        return {"noise_ips": 0, "source": "greynoise", "error": str(exc)}


def _calculate_risk_score(cve_count: int, critical_cves: int, kev_count: int, shodan_hosts: int, feodo_count: int, greynoise_noise: bool) -> float:
    score = 0.0
    score += min(critical_cves * 0.8, 4.0)
    score += min(shodan_hosts / 200.0, 2.5)
    score += min(kev_count * 1.0, 2.0)
    malice = 0.0
    if feodo_count > 0:
        malice += min(feodo_count * 0.5, 1.0)
    if greynoise_noise:
        malice += 0.5
    score += min(malice, 1.5)
    return round(min(score, 10.0), 2)


async def _build_vendor_profile(vendor_id: str) -> VendorProfile:
    registry = VENDOR_REGISTRY.get(vendor_id)
    if not registry:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' no registrado")

    cisa_task = asyncio.create_task(_fetch_cisa_kev(registry["name"]))
    shodan_task = asyncio.create_task(_fetch_shodan(registry["name"]))
    feodo_task = asyncio.create_task(_fetch_feodo(registry.get("domains", [])))
    greynoise_task = asyncio.create_task(_fetch_greynoise(registry.get("domains", [])))

    cisa_data = await cisa_task
    shodan_data = await shodan_task
    feodo_data = await feodo_task
    greynoise_data = await greynoise_task

    critical_cves = sum(1 for c in cisa_data.get("cves", []) if "critical" in str(c.get("vulnerability", "")).lower())
    risk_score = _calculate_risk_score(
        cve_count=cisa_data.get("count", 0), critical_cves=critical_cves,
        kev_count=cisa_data.get("count", 0), shodan_hosts=shodan_data.get("hosts", 0),
        feodo_count=feodo_data.get("count", 0), greynoise_noise=greynoise_data.get("noise_ips", 0) > 0,
    )

    sources_ok = sum(1 for d in [cisa_data, shodan_data, feodo_data, greynoise_data] if not d.get("error"))
    data_quality = "complete" if sources_ok == 4 else ("partial" if sources_ok >= 2 else "degraded")
    sources = [d["source"] for d in [cisa_data, shodan_data, feodo_data, greynoise_data] if not d.get("error")]

    return VendorProfile(
        id=vendor_id, name=registry["name"], category=registry["category"],
        products=registry.get("products", []), domains=registry.get("domains", []),
        risk_score=risk_score, cve_count=cisa_data.get("count", 0), critical_cves=critical_cves,
        kev_count=cisa_data.get("count", 0), shodan_exposed_hosts=shodan_data.get("hosts", 0),
        shodan_services=shodan_data.get("services", []), feodo_ips=feodo_data.get("count", 0),
        greynoise_noise=greynoise_data.get("noise_ips", 0) > 0,
        dependencies=registry.get("dependencies", 0), third_parties=registry.get("third_parties", 0),
        data_quality=data_quality, sources=sources,
    )


@router.get("/vendors")
async def list_vendors(
    current_user: User = Depends(require_role(["full", "admin"])),
    _rate_limit: bool = Depends(rate_limit_standard),
    category: Optional[str] = Query(None, pattern=r"^(software|security|infrastructure|cloud|hardware|devops|networking|iot|other)$"),
    min_risk: Optional[float] = Query(None, ge=0.0, le=10.0),
    max_risk: Optional[float] = Query(None, ge=0.0, le=10.0),
):
    tasks = [asyncio.create_task(_build_vendor_profile(vid)) for vid in VENDOR_REGISTRY]
    profiles = await asyncio.gather(*tasks, return_exceptions=True)
    vendors = []
    for p in profiles:
        if isinstance(p, Exception):
            logger.error("scm_vendor_build_failed", error=str(p))
            continue
        if category and p.category != category:
            continue
        if min_risk is not None and p.risk_score < min_risk:
            continue
        if max_risk is not None and p.risk_score > max_risk:
            continue
        vendors.append(p.model_dump())
    vendors.sort(key=lambda x: x["risk_score"], reverse=True)
    return {"vendors": vendors, "total": len(vendors), "filters": {"category": category, "min_risk": min_risk, "max_risk": max_risk},
            "timestamp": datetime.now(timezone.utc).isoformat(), "data_freshness": "realtime_with_cache"}


@router.get("/vendor/{vendor_id}")
async def get_vendor(vendor_id: str, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    profile = await _build_vendor_profile(vendor_id)
    cisa = await _fetch_cisa_kev(profile.name)
    return {"profile": profile.model_dump(), "cisa_kev_details": cisa.get("cves", []),
            "recommendations": _generate_recommendations(profile, cisa),
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/risks")
async def get_supply_chain_risks(current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    tasks = [asyncio.create_task(_build_vendor_profile(vid)) for vid in VENDOR_REGISTRY]
    profiles = await asyncio.gather(*tasks, return_exceptions=True)
    valid = [p for p in profiles if not isinstance(p, Exception)]
    if not valid:
        raise HTTPException(status_code=503, detail="No se pudieron obtener datos de inteligencia")
    avg_risk = sum(p.risk_score for p in valid) / len(valid)
    high_risk = [p for p in valid if p.risk_score >= 7.0]
    critical = [p for p in valid if p.critical_cves > 0 or p.kev_count > 0]
    cat_risks: Dict[str, List[float]] = {}
    for p in valid:
        cat_risks.setdefault(p.category, []).append(p.risk_score)
    cat_avg = {cat: round(sum(s)/len(s), 2) for cat, s in cat_risks.items()}
    return {"overall_risk_score": round(avg_risk, 2), "risk_level": _risk_level(avg_risk),
            "vendor_count": len(valid), "high_risk_vendors": len(high_risk), "critical_vendors": len(critical),
            "category_breakdown": cat_avg,
            "top_risks": [p.model_dump() for p in sorted(valid, key=lambda x: x.risk_score, reverse=True)[:5]],
            "recommendations": _generate_aggregate_recommendations(valid),
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/vendor/{vendor_id}/assess")
async def assess_vendor(vendor_id: str, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    for prefix in ["cisa_kev", "shodan", "feodo", "greynoise"]:
        key = f"{prefix}:{vendor_id.lower()}"
        if key in _cache:
            del _cache[key]
    profile = await _build_vendor_profile(vendor_id)
    cisa = await _fetch_cisa_kev(profile.name)
    return {"profile": profile.model_dump(),
            "assessment": RiskAssessment(vendor_id=vendor_id, overall_risk=profile.risk_score,
                recommendations=_generate_recommendations(profile, cisa)).model_dump(),
            "cache_bypassed": True, "timestamp": datetime.now(timezone.utc).isoformat()}


def _risk_level(score: float) -> str:
    if score >= 7.0: return "CRITICAL"
    if score >= 5.0: return "HIGH"
    if score >= 3.0: return "MEDIUM"
    return "LOW"


def _generate_recommendations(profile: VendorProfile, cisa: Dict[str, Any]) -> List[str]:
    recs = []
    if profile.critical_cves > 0:
        recs.append(f"CRÍTICO: {profile.critical_cves} CVEs críticos activos. Aplicar parches inmediatamente.")
    if profile.kev_count > 0:
        recs.append(f"ALTO: {profile.kev_count} vulnerabilidades en catálogo KEV de CISA (explotación conocida).")
    if profile.shodan_exposed_hosts > 100:
        recs.append(f"MEDIO: {profile.shodan_exposed_hosts} hosts expuestos en internet. Revisar superficie de ataque.")
    if profile.feodo_ips > 0:
        recs.append(f"CRÍTICO: {profile.feodo_ips} IPs asociadas al vendor detectadas en botnet Feodo.")
    if profile.greynoise_noise:
        recs.append("MEDIO: Actividad de scan/botnet detectada en IPs del vendor (GreyNoise).")
    if profile.data_quality == "degraded":
        recs.append("ADVERTENCIA: Calidad de datos degradada. Algunas fuentes de inteligencia no respondieron.")
    if not recs:
        recs.append("Riesgo aceptable. Mantener monitoreo continuo.")
    return recs


def _generate_aggregate_recommendations(profiles: List[VendorProfile]) -> List[str]:
    recs = []
    critical_count = sum(1 for p in profiles if p.risk_score >= 7.0)
    if critical_count > 0:
        recs.append(f"{critical_count} vendor(s) con riesgo CRÍTICO requieren atención inmediata.")
    kev_vendors = [p.name for p in profiles if p.kev_count > 0]
    if kev_vendors:
        recs.append(f"Vendors con vulnerabilidades KEV: {', '.join(kev_vendors)}. Verificar parches.")
    exposed = sum(p.shodan_exposed_hosts for p in profiles)
    if exposed > 500:
        recs.append(f"{exposed} hosts expuestos agregados en Shodan. Auditar superficie de ataque.")
    feodo_total = sum(p.feodo_ips for p in profiles)
    if feodo_total > 0:
        recs.append(f"{feodo_total} IPs maliciosas detectadas en Feodo Tracker. Investigar compromiso.")
    if not recs:
        recs.append("Cadena de suministro con riesgo aceptable. Mantener monitoreo continuo.")
    return recs
