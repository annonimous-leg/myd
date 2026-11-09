"""Cyber Router - OSINT reconnaissance endpoints.

Provides endpoints for:
- Shodan device search and host lookup
- Censys host/certificate/website search
- GreyNoise IP classification
- CISA KEV catalog
- Malware feeds (Feodo, URLhaus)
"""
from core.rate_limit import rate_limit_standard, rate_limit_strict

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List

from routers.auth import require_role
from services.malware.shodan_connector import ShodanConnector
from services.malware.censys import CensysClient
from services.malware.grey_noise import GreyNoiseClient
from services.malware.cisa_kev import CISAKEVClient
from services.malware.feodo_tracker import FeodoTrackerClient
from services.malware.urlhaus import URLhausClient

router = APIRouter(tags=["cyber"])


# ─── Shodan ───

@router.get("/shodan/search",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def shodan_search(
    query: str = Query(..., description="Shodan search query"),
    page: int = Query(1, ge=1),
    facets: Optional[str] = Query(None), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Search Shodan for exposed devices."""
    client = ShodanConnector()
    facet_list = facets.split(",") if facets else None
    result = client.search(query, facets=facet_list, page=page)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/shodan/host/{ip}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def shodan_host(ip: str, _rate_limit: bool = Depends(rate_limit_standard)):
    """Get detailed info about a specific IP."""
    client = ShodanConnector()
    result = client.host(ip)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/shodan/ics",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def shodan_ics(country: Optional[str] = None, _rate_limit: bool = Depends(rate_limit_standard)):
    """Search for Industrial Control Systems."""
    client = ShodanConnector()
    result = client.search_ics(country=country)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/shodan/webcams",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def shodan_webcams(country: Optional[str] = None, _rate_limit: bool = Depends(rate_limit_standard)):
    """Search for exposed webcams/IP cameras."""
    client = ShodanConnector()
    result = client.search_webcams(country=country)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/shodan/vulns/{cve}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def shodan_vulns(cve: str, _rate_limit: bool = Depends(rate_limit_standard)):
    """Search devices vulnerable to specific CVE."""
    client = ShodanConnector()
    result = client.search_vulns(cve)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


# ─── Censys ───

@router.get("/censys/hosts",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def censys_hosts(
    query: str = Query(..., description="Censys search query"),
    per_page: int = Query(50, ge=1, le=100), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Search Censys for IPv4 hosts."""
    client = CensysClient()
    result = client.search_hosts(query, per_page=per_page)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/censys/host/{ip}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def censys_host(ip: str, _rate_limit: bool = Depends(rate_limit_standard)):
    """Get detailed host information."""
    client = CensysClient()
    result = client.view_host(ip)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/censys/certificates",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def censys_certs(
    query: str = Query(..., description="Certificate search query"),
    per_page: int = Query(50, ge=1, le=100), _rate_limit: bool = Depends(rate_limit_standard)
):
    """Search SSL/TLS certificates."""
    client = CensysClient()
    result = client.search_certificates(query, per_page=per_page)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.get("/censys/country/{country}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def censys_by_country(country: str, services: Optional[str] = None, _rate_limit: bool = Depends(rate_limit_standard)):
    """Find hosts in a specific country."""
    client = CensysClient()
    svc_list = services.split(",") if services else None
    result = client.get_hosts_by_country(country, services=svc_list)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


# ─── GreyNoise ───

@router.get("/greynoise/ip/{ip}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def greynoise_ip(ip: str, _rate_limit: bool = Depends(rate_limit_standard)):
    """Check IP classification in GreyNoise."""
    client = GreyNoiseClient()
    result = client.ip_context(ip)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


@router.post("/greynoise/batch",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def greynoise_batch(ips: List[str], _rate_limit: bool = Depends(rate_limit_strict)):
    """Check multiple IPs at once."""
    client = GreyNoiseClient()
    result = client.multi_context(ips)
    return {"results": result}


@router.get("/greynoise/noise",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def greynoise_noise(_rate_limit: bool = Depends(rate_limit_standard)):
    """Get noise/range data."""
    client = GreyNoiseClient()
    # Sample common IPs
    sample_ips = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
    results = client.multi_context(sample_ips)
    return {"results": results}


# ─── CISA KEV ───

@router.get("/cisa-kev",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def cisa_kev(_rate_limit: bool = Depends(rate_limit_standard)):
    """Get CISA Known Exploited Vulnerabilities catalog."""
    client = CISAKEVClient()
    return client.fetch()


@router.get("/cisa-kev/vendor/{vendor}",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def cisa_kev_vendor(vendor: str, _rate_limit: bool = Depends(rate_limit_standard)):
    """Filter KEV by vendor."""
    client = CISAKEVClient()
    return client.get_by_vendor(vendor)


@router.get("/cisa-kev/critical",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def cisa_kev_critical(days: int = Query(7, ge=1, le=365), _rate_limit: bool = Depends(rate_limit_standard)):
    """Get critical vulnerabilities due within N days."""
    client = CISAKEVClient()
    return client.get_critical(days=days)


@router.get("/cisa-kev/ransomware",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def cisa_kev_ransomware(_rate_limit: bool = Depends(rate_limit_standard)):
    """Get vulnerabilities used in ransomware campaigns."""
    client = CISAKEVClient()
    return client.get_ransomware()


@router.get("/cisa-kev/stats",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def cisa_kev_stats(_rate_limit: bool = Depends(rate_limit_standard)):
    """Get KEV statistics."""
    client = CISAKEVClient()
    return client.get_stats()


# ─── Malware Feeds ───

@router.get("/malware/feodo",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def malware_feodo(limit: int = Query(100, ge=1, le=500), _rate_limit: bool = Depends(rate_limit_standard)):
    """Get Feodo Tracker botnet C2 IPs."""
    client = FeodoTrackerClient()
    ips = client.fetch(limit=limit)
    return {"feodo": [ip.to_dict() for ip in ips], "count": len(ips)}


@router.get("/malware/urlhaus",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def malware_urlhaus(limit: int = Query(50, ge=1, le=1000), _rate_limit: bool = Depends(rate_limit_standard)):
    """Get URLhaus malicious URLs."""
    client = URLhausClient()
    urls = client.fetch_recent(limit=limit)
    return {"urlhaus": urls, "count": len(urls)}


@router.get("/malware/stats",
    dependencies=[Depends(require_role(["full", "admin"]))])
async def malware_stats(_rate_limit: bool = Depends(rate_limit_standard)):
    """Get combined malware feed statistics."""
    feodo = FeodoTrackerClient()
    urlhaus = URLhausClient()

    feodo_data = feodo.fetch(limit=100)
    urlhaus_data = urlhaus.fetch_recent(limit=100)

    return {
        "feodo": {"count": len(feodo_data), "stats": feodo.get_stats()},
        "urlhaus": {"count": len(urlhaus_data), "stats": urlhaus.get_stats()},
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    }
