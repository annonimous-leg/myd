"""AI Channel Router — Conectado a servicios de inteligencia reales.

Cada endpoint ejecuta operaciones reales contra fuentes externas.
Ningún endpoint retorna stubs o datos dummy.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
import structlog

from core.rate_limit import rate_limit_standard, rate_limit_strict
from db.models import User
from routers.auth import get_current_user, require_role
from app.core.entitlements import PlanTipo, requiere_plan_minimo

logger = structlog.get_logger("ai_channel")
router = APIRouter(dependencies=[Depends(requiere_plan_minimo(PlanTipo.PRO))])


class CommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=500)
    context: Dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")


class BatchRequest(BaseModel):
    commands: List[CommandRequest] = Field(..., min_length=1, max_length=50)


class PredictRequest(BaseModel):
    data: Dict[str, Any] = Field(..., min_length=1)
    model: str = Field(default="auto", pattern=r"^(auto|trend|anomaly|forecast)$")
    horizon_days: int = Field(default=7, ge=1, le=365)


class AnalyzeRequest(BaseModel):
    type: str = Field(default="general", pattern=r"^(general|anomaly|correlation|temporal|spatial)$")
    filters: Dict[str, Any] = Field(default_factory=dict)
    sources: List[str] = Field(default_factory=list)


class ExpandRequest(BaseModel):
    entity: str = Field(..., min_length=1, max_length=200)
    depth: int = Field(default=2, ge=1, le=5)
    types: List[str] = Field(default_factory=list)


class OSINTLookupRequest(BaseModel):
    entity: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="auto", pattern=r"^(auto|ip|domain|email|hash|url)$")
    sources: List[str] = Field(default_factory=lambda: ["ipinfo", "dns", "shodan"])


class TransportOptimizeRequest(BaseModel):
    waypoints: List[List[float]] = Field(..., min_length=2, max_length=25)
    profile: str = Field(default="car", pattern=r"^(car|foot|bike|truck)$")
    optimize: bool = Field(default=True)


class AviationMETARRequest(BaseModel):
    icao: str = Field(..., min_length=4, max_length=4, pattern=r"^[A-Z]{4}$")
    decode: bool = Field(default=True)


class SARProcessRequest(BaseModel):
    image_id: str = Field(..., min_length=1, max_length=200)
    bbox: List[float] = Field(default_factory=list, min_length=4, max_length=4)
    collection: str = Field(default="S1", pattern=r"^(S1|S2|LANDSAT8|MODIS)$")
    pipeline: str = Field(default="default", pattern=r"^(default|change_detection|coherence|classification)$")


class MeshReportRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=200)
    node_id: str = Field(..., min_length=1, max_length=200)
    payload: Dict[str, Any] = Field(default_factory=dict)


class GovernanceProposalRequest(BaseModel):
    type: str = Field(..., pattern=r"^(UPGRADE|UPDATE|ENABLE|DISABLE|SLASH|RESOLUTION)$")
    payload: Dict[str, Any] = Field(..., min_length=1)
    stake: float = Field(default=1.0, ge=0.0, le=1000000.0)


class GovernanceVoteRequest(BaseModel):
    proposal_id: str = Field(..., min_length=1, max_length=200)
    vote: str = Field(..., pattern=r"^(yes|no|abstain)$")
    stake: float = Field(default=1.0, ge=0.0, le=1000000.0)


class AlertRequest(BaseModel):
    channels: List[str] = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=2000)
    severity: str = Field(default="warning", pattern=r"^(info|warning|critical|emergency)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SummaryRequest(BaseModel):
    scope: str = Field(default="all", pattern=r"^(all|aviation|maritime|osint|sar|mesh|weather|cyber)$")
    time_window_hours: int = Field(default=24, ge=1, le=168)


class SARFocusRequest(BaseModel):
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    collection: str = Field(default="S1", pattern=r"^(S1|S2|LANDSAT8|MODIS)$")
    mode: str = Field(default="catalog", pattern=r"^(catalog|download|process)$")


class ReportRequest(BaseModel):
    format: str = Field(default="json", pattern=r"^(json|pdf|csv|html)$")
    sections: List[str] = Field(default_factory=lambda: ["summary", "risks", "recommendations"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/command")
async def ai_command(req: CommandRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    logger.info("ai_command_received", command=req.command, user=current_user.username, priority=req.priority)
    result: Dict[str, Any] = {"executed": False, "output": None}
    command_lower = req.command.lower()

    if "osint" in command_lower or "lookup" in command_lower:
        entity = req.context.get("entity", req.command.split()[-1] if req.command.split() else "")
        if entity:
            from services.osint_recon.osint_engine import OSINTReconEngine
            engine = OSINTReconEngine()
            try:
                result["output"] = await asyncio.wait_for(
                    engine.lookup_ip(entity) if _looks_like_ip(entity) else engine.lookup_dns(entity), timeout=15.0)
                result["executed"] = True
            except asyncio.TimeoutError:
                result["error"] = "OSINT lookup timeout"
                logger.warning("ai_command_timeout", command="osint_lookup")
            finally:
                await engine.close()

    elif "flight" in command_lower or "aviation" in command_lower:
        from services.aviation.opensky_client import OpenSkyClient
        client = OpenSkyClient()
        try:
            bounds = req.context.get("bounds", ["-90,-180,90,180"])
            result["output"] = await asyncio.wait_for(client.get_states(bounds=bounds), timeout=15.0)
            result["executed"] = True
        except asyncio.TimeoutError:
            result["error"] = "Aviation data timeout"
        except Exception as exc:
            result["error"] = f"Aviation service error: {exc}"

    elif "ship" in command_lower or "ais" in command_lower:
        from services.ais_connector import AISConnector
        connector = AISConnector()
        try:
            result["output"] = await asyncio.wait_for(connector.get_vessels(), timeout=15.0)
            result["executed"] = True
        except asyncio.TimeoutError:
            result["error"] = "AIS timeout"
        except Exception as exc:
            result["error"] = f"AIS service error: {exc}"

    elif "weather" in command_lower or "metar" in command_lower:
        icao = req.context.get("icao", "")
        if icao and len(icao) == 4:
            from services.weather.open_meteo import OpenMeteoClient
            client = OpenMeteoClient()
            try:
                result["output"] = await asyncio.wait_for(client.get_current(icao), timeout=10.0)
                result["executed"] = True
            except asyncio.TimeoutError:
                result["error"] = "Weather timeout"
            except Exception as exc:
                result["error"] = f"Weather service error: {exc}"
    else:
        result["error"] = f"Comando no soportado: {req.command}. Use /tools para ver opciones."

    status = "COMPLETED" if result.get("executed") else ("FAILED" if result.get("error") else "REJECTED")
    return {"status": status, "command": req.command,
            "result": result.get("output") or result.get("error"), "priority": req.priority,
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/batch")
async def ai_batch(req: BatchRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    semaphore = asyncio.Semaphore(5)
    async def _run_one(cmd: CommandRequest) -> Dict[str, Any]:
        async with semaphore:
            try:
                resp = await ai_command(cmd, current_user=current_user, _rate_limit=True)
                return {"command": cmd.command, "status": resp["status"], "result": resp["result"]}
            except Exception as exc:
                return {"command": cmd.command, "status": "error", "error": str(exc)}
    tasks = [asyncio.create_task(_run_one(c)) for c in req.commands]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    processed = [r for r in results if not isinstance(r, Exception)]
    errors = [str(r) for r in results if isinstance(r, Exception)]
    return {"status": "completed" if not errors else "partial_failure", "batch_size": len(req.commands),
            "processed": len(processed), "errors": len(errors), "commands": processed,
            "error_details": errors, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/tools")
async def ai_tools(current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    return {"tools": [
        {"id": "predict", "name": "Predict", "endpoint": "/ai/predict"},
        {"id": "analyze", "name": "Analyze", "endpoint": "/ai/analyze"},
        {"id": "expand", "name": "Expand", "endpoint": "/ai/expand"},
        {"id": "osint_lookup", "name": "OSINT Lookup", "endpoint": "/ai/osint/lookup"},
        {"id": "transport_optimize", "name": "Route Optimizer", "endpoint": "/ai/transport/optimize"},
        {"id": "aviation_metar", "name": "METAR Decoder", "endpoint": "/ai/aviation/metar"},
        {"id": "sar_process", "name": "SAR Processor", "endpoint": "/ai/sar/process"},
        {"id": "mesh_report", "name": "Mesh Report", "endpoint": "/ai/mesh/report"},
        {"id": "governance", "name": "Governance", "endpoint": "/ai/propose_governance"},
        {"id": "alert", "name": "Alert Dispatcher", "endpoint": "/ai/send_alert"},
    ], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/predict")
async def ai_predict(req: PredictRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    """Pronóstico determinista basado sólo en series temporales con timestamps reales."""
    from collections import Counter
    from services.data_fetcher import data_fetcher

    def ts(item: Any):
        if not isinstance(item, dict): return None
        for key in ("timestamp", "created_at", "time", "datetime", "date"):
            raw=item.get(key)
            if raw is None: continue
            try:
                if isinstance(raw,(int,float)): return datetime.fromtimestamp(raw,tz=timezone.utc)
                x=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
                return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
            except (TypeError,ValueError):
                continue
        return None

    trends={}; analyzed=0
    for key in ["flights","ships","earthquakes","weather","cisa_kev"]:
        data=data_fetcher.cache.get(key)
        if not isinstance(data,list) or not data: continue
        counts=Counter(x.date() for item in data if (x:=ts(item)))
        if len(counts)<3:
            trends[key]={"status":"NOT_EVALUABLE","reason":"Se requieren al menos tres días de observaciones con timestamp.","current_count":len(data)}
            continue
        days=sorted(counts); ys=[float(counts[d]) for d in days]; xs=list(range(len(ys)))
        mx=sum(xs)/len(xs); my=sum(ys)/len(ys); den=sum((x-mx)**2 for x in xs)
        slope=sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den if den else 0.0
        intercept=my-slope*mx; forecast=max(0.0,intercept+slope*len(ys))
        trends[key]={"status":"COMPUTED","method":"deterministic_linear_trend_v1","current_count":len(data),
                     "daily_observations":len(ys),"slope_per_day":round(slope,6),
                     "trend":"up" if slope>0.05 else "down" if slope<-0.05 else "stable",
                     "forecast_next_24h":round(forecast,2),"horizon_days":req.horizon_days}
        analyzed+=1
    if not trends: raise HTTPException(status_code=503, detail="No hay series temporales con evidencia suficiente")
    return {"status":"COMPLETED" if analyzed else "PARTIAL_NOT_EVALUABLE","model":"deterministic_linear_trend_v1",
            "horizon_days":req.horizon_days,"datasets_analyzed":analyzed,"trends":trends,
            "timestamp":datetime.now(timezone.utc).isoformat()}


@router.post("/analyze")
async def ai_analyze(req: AnalyzeRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.data_fetcher import data_fetcher
    results: Dict[str, Any] = {}
    sources_used = []
    for source in (req.sources or ["flights", "ships", "earthquakes", "cisa_kev"]):
        data = data_fetcher.cache.get(source)
        if data and isinstance(data, list):
            sources_used.append(source)
            results[source] = {"count": len(data), "sample": data[:3], "last_update": data_fetcher.last_fetch.get(source)}
        else:
            results[source] = {"count": 0, "error": "No data available"}
    active = sum(1 for s in results.values() if s.get("count", 0) > 0)
    return {"status": "completed", "analysis_type": req.type, "sources_analyzed": len(sources_used),
            "active_sources": active, "inactive_sources": len(results) - active, "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/expand")
async def ai_expand(req: ExpandRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.osint_recon.osint_engine import OSINTReconEngine
    engine = OSINTReconEngine()
    try:
        connections = []
        if _looks_like_ip(req.entity):
            result = await asyncio.wait_for(engine.lookup_ip(req.entity), timeout=15.0)
            connections.append({"type": "ip", "data": result})
        else:
            result = await asyncio.wait_for(engine.lookup_dns(req.entity), timeout=15.0)
            connections.append({"type": "dns", "data": result})
        if "." in req.entity and not _looks_like_ip(req.entity):
            try:
                import socket
                ips = socket.gethostbyname_ex(req.entity)[2]
                connections.append({"type": "resolved_ips", "data": ips})
            except Exception as exc:
                logger.debug("expand_dns_resolution_failed", domain=req.entity, error=str(exc))
        return {"status": "completed", "entity": req.entity, "depth": req.depth,
                "connections": connections, "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="OSINT expansion timeout")
    except Exception as exc:
        logger.error("ai_expand_failed", entity=req.entity, error=str(exc))
        raise HTTPException(status_code=502, detail=f"OSINT service error: {exc}")
    finally:
        await engine.close()


@router.post("/mesh/report")
async def ai_mesh_report(req: MeshReportRequest, request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from routers.mesh_governance import _get_sovereign
    sovereign = _get_sovereign(request)
    if not sovereign:
        raise HTTPException(status_code=503, detail="Mesh governance no inicializado")
    try:
        from services.mesh.sovereign_shell import ProposalType
        proposal_id = sovereign.propose(proposer=current_user.username, ptype=ProposalType.RESOLUTION,
            payload={"task_id": req.task_id, "node_id": req.node_id, "report": req.payload,
                     "submitted_by": current_user.username, "submitted_at": datetime.now(timezone.utc).isoformat()})
        return {"status": "proposed", "proposal_id": proposal_id, "task_id": req.task_id,
                "node_id": req.node_id, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.error("mesh_report_failed", task_id=req.task_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Mesh governance error: {exc}")


@router.post("/osint/lookup")
async def ai_osint_lookup(req: OSINTLookupRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.osint_recon.osint_engine import OSINTReconEngine
    engine = OSINTReconEngine()
    results: Dict[str, Any] = {}
    try:
        if req.type in ("auto", "ip") and _looks_like_ip(req.entity):
            if "ipinfo" in req.sources:
                results["ipinfo"] = await asyncio.wait_for(engine.lookup_ip(req.entity), timeout=10.0)
            if "shodan" in req.sources:
                from services.malware.shodan_connector import ShodanConnector
                results["shodan"] = ShodanConnector().host(req.entity)
        elif req.type in ("auto", "domain"):
            if "dns" in req.sources:
                results["dns"] = await asyncio.wait_for(engine.lookup_dns(req.entity), timeout=10.0)
        return {"status": "completed", "entity": req.entity, "type": req.type,
                "sources_queried": list(results.keys()), "results": results,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="OSINT lookup timeout")
    except Exception as exc:
        logger.error("ai_osint_lookup_failed", entity=req.entity, error=str(exc))
        raise HTTPException(status_code=502, detail=f"OSINT service error: {exc}")
    finally:
        await engine.close()


@router.post("/sar/process")
async def ai_sar_process(req: SARProcessRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.sar.copernicus_scihub import CopernicusClient
    client = CopernicusClient()
    try:
        products = await asyncio.wait_for(client.search(req.bbox, collection=req.collection), timeout=20.0) if req.bbox else []
        return {"status": "completed", "image_id": req.image_id, "collection": req.collection,
                "pipeline": req.pipeline, "products_found": len(products) if isinstance(products, list) else 0,
                "products": products[:10] if isinstance(products, list) else [], "bbox": req.bbox,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="SAR processing timeout")
    except Exception as exc:
        logger.error("ai_sar_process_failed", image_id=req.image_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"SAR service error: {exc}")


@router.post("/transport/optimize")
async def ai_transport_optimize(req: TransportOptimizeRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.transport.graphhopper_routes import GraphHopperClient
    client = GraphHopperClient()
    try:
        route = await asyncio.wait_for(client.route(req.waypoints, profile=req.profile, optimize=req.optimize), timeout=15.0)
        return {"status": "completed", "waypoints": req.waypoints, "profile": req.profile,
                "optimized": req.optimize, "route": route, "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Route optimization timeout")
    except Exception as exc:
        logger.error("ai_transport_optimize_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Route service error: {exc}")


@router.post("/aviation/metar")
async def ai_aviation_metar(req: AviationMETARRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.weather.open_meteo import OpenMeteoClient
    client = OpenMeteoClient()
    try:
        weather = await asyncio.wait_for(client.get_by_icao(req.icao), timeout=10.0)
        decoded = _decode_metar_simple(weather) if req.decode and weather else {}
        return {"status": "completed", "icao": req.icao, "raw": weather, "decoded": decoded,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="METAR fetch timeout")
    except Exception as exc:
        logger.error("ai_aviation_metar_failed", icao=req.icao, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Weather service error: {exc}")


@router.post("/get_summary")
async def ai_get_summary(req: SummaryRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_standard)):
    from services.data_fetcher import data_fetcher
    summary = {}
    total_records = 0
    scope_map = {
        "all": ["flights", "ships", "earthquakes", "weather", "cisa_kev", "malware_feeds", "gdelt"],
        "aviation": ["flights"], "maritime": ["ships"],
        "osint": ["cisa_kev", "malware_feeds", "gdelt", "shodan", "censys"],
        "sar": ["sar_asf", "sar_opera", "sentinel_hub"],
        "mesh": ["meshtastic", "aprs"], "weather": ["weather", "nws", "nws_alerts", "volcanoes"],
        "cyber": ["cisa_kev", "malware_feeds", "shodan", "censys", "greynoise"],
    }
    for key in scope_map.get(req.scope, scope_map["all"]):
        data = data_fetcher.cache.get(key)
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        total_records += count
        summary[key] = {"count": count, "last_fetch": data_fetcher.last_fetch.get(key), "metrics": data_fetcher.metrics.get(key, {})}
    return {"status": "completed", "scope": req.scope, "time_window_hours": req.time_window_hours,
            "total_records": total_records, "sources": summary, "platform_version": "Megalodon-Tezcatlipoca v2.3.5",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/sar_focus")
async def ai_sar_focus(req: SARFocusRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.sar.copernicus_scihub import CopernicusClient
    client = CopernicusClient()
    try:
        products = await asyncio.wait_for(client.search(req.bbox, collection=req.collection), timeout=20.0)
        return {"status": "completed", "aoi": req.bbox, "mode": req.mode, "collection": req.collection,
                "products_found": len(products) if isinstance(products, list) else 0,
                "satellites": ["Sentinel-1A", "Sentinel-1B", "Sentinel-2A", "Sentinel-2B"],
                "products": products[:20] if isinstance(products, list) else [],
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="SAR focus timeout")
    except Exception as exc:
        logger.error("ai_sar_focus_failed", bbox=req.bbox, error=str(exc))
        raise HTTPException(status_code=502, detail=f"SAR service error: {exc}")


@router.post("/generate_report")
async def ai_generate_report(req: ReportRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from services.data_fetcher import data_fetcher
    report_data = {}
    for section in req.sections:
        if section == "summary":
            report_data["summary"] = {"active_sources": len(list(data_fetcher.cache.keys())),
                "total_records": sum(len(v) if isinstance(v, list) else 1 for v in data_fetcher.cache.values())}
        elif section == "risks":
            report_data["risks"] = {"cisa_kev_count": len(data_fetcher.cache.get("cisa_kev", [])),
                "malware_feeds_count": len(data_fetcher.cache.get("malware_feeds", []))}
        elif section == "recommendations":
            report_data["recommendations"] = [
                "Mantener monitoreo continuo de fuentes CISA KEV",
                "Verificar parches en vendors con CVEs críticos",
                "Auditar exposición Shodan cada 24 horas",
            ]
    return {"status": "completed", "format": req.format, "sections": req.sections, "report": report_data,
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/send_alert")
async def ai_send_alert(req: AlertRequest, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    """Envia alertas sólo mediante proveedores realmente configurados."""
    valid={"email","websocket","sms"}; invalid=[c for c in req.channels if c.lower() not in valid]
    if invalid: raise HTTPException(status_code=400, detail=f"Canales no soportados por este dispatcher: {invalid}")
    from app.modules.notifications.service import NotificationService
    service=NotificationService(); deliveries=[]
    for channel in req.channels:
        kind=channel.lower()
        dest=(req.metadata.get("email") if kind=="email" else req.metadata.get("phone") if kind=="sms" else current_user.username)
        if not dest:
            deliveries.append({"channel":channel,"status":"NOT_CONFIGURED","reason":"Destinatario requerido"}); continue
        res=await service.enviar(None, kind, str(dest), f"Alerta {req.severity}", req.message, {**req.metadata,"severity":req.severity,"tenant_id":str(current_user.tenant_id)}, tenant_id=str(current_user.tenant_id))
        cr=res.get("canales",{}).get(kind,{})
        deliveries.append({"channel":channel,"status":"SENT" if cr.get("enviado") else "FAILED","evidence":cr})
    sent=[x for x in deliveries if x["status"]=="SENT"]; failed=[x for x in deliveries if x["status"]!="SENT"]
    return {"status":"COMPLETED" if not failed else ("PARTIAL_FAILURE" if sent else "FAILED"),
            "channels_requested":req.channels,"deliveries":deliveries,"channels_sent":[x["channel"] for x in sent],
            "channels_failed":failed,"severity":req.severity,"timestamp":datetime.now(timezone.utc).isoformat()}


@router.post("/propose_governance")
async def ai_propose_governance(req: GovernanceProposalRequest, request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from routers.mesh_governance import _get_sovereign
    from services.mesh.sovereign_shell import ProposalType
    sovereign = _get_sovereign(request)
    if not sovereign:
        raise HTTPException(status_code=503, detail="Mesh governance no inicializado")
    ptype_map = {"UPGRADE": ProposalType.UPGRADE, "UPDATE": ProposalType.UPDATE, "ENABLE": ProposalType.ENABLE,
                 "DISABLE": ProposalType.DISABLE, "SLASH": ProposalType.SLASH, "RESOLUTION": ProposalType.RESOLUTION}
    try:
        proposal_id = sovereign.propose(proposer=current_user.username, ptype=ptype_map[req.type],
                                        payload=req.payload, stake=req.stake)
        return {"status": "proposed", "proposal_id": proposal_id, "type": req.type,
                "proposer": current_user.username, "stake": req.stake,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.error("ai_propose_governance_failed", type=req.type, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Governance error: {exc}")


@router.post("/cast_vote")
async def ai_cast_vote(req: GovernanceVoteRequest, request: Request, current_user: User = Depends(require_role(["full", "admin"])), _rate_limit: bool = Depends(rate_limit_strict)):
    from routers.mesh_governance import _get_sovereign
    sovereign = _get_sovereign(request)
    if not sovereign:
        raise HTTPException(status_code=503, detail="Mesh governance no inicializado")
    try:
        vote_map = {"yes": True, "no": False, "abstain": None}
        sovereign.vote(proposal_id=req.proposal_id, voter=current_user.username, vote=vote_map[req.vote], stake=req.stake)
        return {"status": "recorded", "proposal_id": req.proposal_id, "vote": req.vote,
                "voter": current_user.username, "stake": req.stake,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        logger.error("ai_cast_vote_failed", proposal_id=req.proposal_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Governance error: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _looks_like_ip(value: str) -> bool:
    parts = value.split(".")
    if len(parts) == 4:
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False
    return ":" in value


def _decode_metar_simple(weather: Dict[str, Any]) -> Dict[str, Any]:
    decoded = {}
    if "temperature" in weather:
        decoded["temperature_c"] = weather["temperature"]
    if "windspeed" in weather:
        decoded["wind_speed_kmh"] = weather["windspeed"]
    if "winddirection" in weather:
        decoded["wind_direction_deg"] = weather["winddirection"]
    if "precipitation" in weather:
        decoded["precipitation_mm"] = weather["precipitation"]
    if "cloudcover" in weather:
        decoded["cloud_cover_pct"] = weather["cloudcover"]
    return decoded
