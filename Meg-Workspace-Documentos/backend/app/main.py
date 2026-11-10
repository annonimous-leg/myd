# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Megalodon CostOS v4 - Backend Empresarial
FastAPI application factory con arquitectura modular + WebSocket.
"""
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.api.v1.router import api_router
from app.api.v1.websocket import manager as ws_manager, router as ws_router
from app.core.errors import MegalodonException
from app.core.observability import RequestContextMiddleware, metrics_endpoint
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.csrf import BrowserOriginCSRFMiddleware
from app.core.tracing import init_telemetry, shutdown_telemetry
from app.core.redis_client import close_redis, get_redis
from app.utils.logging import configure_logging
from app.models.base import engine
import structlog

logger = structlog.get_logger()

# ═══════════════════════════════════════════════════════════════════
# INTEGRACIÓN ZIP 4: TEZCATLIPOCA (geo / OSINT / cyber / aviación / SAR)
# ═══════════════════════════════════════════════════════════════════
# Los routers de Tezcatlipoca comparten el runtime y la identidad de MEGALODON.
# Su espejo local conserva relaciones de recursos, nunca sesiones ni permisos.
# Las migraciones son un paso previo de despliegue; el arranque verifica el
# esquema sin modificarlo. Los adaptadores externos siguen siendo opcionales.
import sys
from pathlib import Path

_TEZCATLIPOCA_PATH = Path(__file__).resolve().parent.parent / "tezcatlipoca"
if str(_TEZCATLIPOCA_PATH) not in sys.path:
    sys.path.insert(0, str(_TEZCATLIPOCA_PATH))

from routers import (  # noqa: E402 -- import tardío: depende del sys.path.insert de arriba
    admin_router as tz_admin_router,
    ai_router as tz_ai_router,
    auth_router as tz_auth_router,
    cyber_router as tz_cyber_router,
    entity_router as tz_entity_router,
    geo_router as tz_geo_router,
    weather_router as tz_weather_router,
    geo_threats_router as tz_geo_threats_router,
    layers_router as tz_layers_router,
    malware_router as tz_malware_router,
    mesh_router as tz_mesh_router,
    osint_router as tz_osint_router,
    snapshots_router as tz_snapshots_router,
    telemetry_router as tz_telemetry_router,
    honeypot_router as tz_honeypot_router,
    transport_router as tz_transport_router,
    aviation_router as tz_aviation_router,
    sar_router as tz_sar_router,
    photogrammetry_router as tz_photogrammetry_router,
    scm_router as tz_scm_router,
    settings_router as tz_settings_router,
    wormhole_router as tz_wormhole_router,
)

# BUG ORIGINAL (encontrado haciendo la tarea C, no estaba en ningún
# audit previo): esta sección solo importaba los ROUTERS de
# tezcatlipoca. Los routers reales (aviation, sar, transport,
# photogrammetry, layers, telemetry, geo, geo_threats, entity_graph)
# leen sus clientes/engines de `request.app.state.X` (p.ej.
# `req.app.state.faa_notams`) -- y esos atributos SOLO se poblaban en
# el lifespan de tezcatlipoca/main.py, que este proceso NUNCA ejecuta
# (aquí solo se importan los `router` objects, ver arriba). Resultado:
# en el deploy real, esos endpoints tiraban 500 (AttributeError sobre
# app.state) sin importar auth o rate limit -- el módulo entero estaba
# roto por un cable sin conectar, no por falta de protección.
#
# AHORA: se replica aquí, verbatim, el mismo bloque de inicialización
# que ya usaba tezcatlipoca/main.py (mismos imports, mismos
# constructores, mismos valores por defecto) -- no se reinventa nada,
# solo se conecta al proceso que de verdad corre en producción. Se
# revisó cada constructor (FAANOTAMClient, AISConnector, etc.): todos
# leen su API key con os.getenv(..., "") y degradan con gracia si falta
# (ver p.ej. AISConnector.connect(), que atrapa su propia excepción y
# solo loguea "Modo simulado" si no hay AISSTREAM_API_KEY) -- así que
# instanciarlos sin credenciales configuradas no revienta nada, esos
# endpoints simplemente devuelven resultados vacíos/no-configurado en
# vez de un 500 por atributo faltante.
from db.models import init_db_async
from services.data_fetcher import DataFetcherEngine
from services.mesh.max_power_peer import MaxPowerPeerEngine
from services.mesh.honeypot import HoneypotEngine
from services.mesh.sprt_slashing import SPRTSlashingFixed
from services.mesh.sovereign_shell import SovereignShell
from services.snapshot_store import SnapshotStore
from services.cctv_pipeline import CCTVPipeline
from services.sigint.sigint_engine import SIGINTEngine
from services.sar_connector import SARConnector
from services.ais_connector import AISConnector
from services.osint_recon.osint_engine import OSINTReconEngine
from services.malware.aggregator import MalwareAggregator
from services.transport.graphhopper_routes import GraphHopperClient
from services.transport.db_bahn_trains import DBTrainClient
from services.transport.gtfs_mobility import GTFSMobilityClient
from services.aviation.faa_notams import FAANOTAMClient
from services.aviation.avwx_engine import AVWXClient
from services.aviation.adsb_exchange import ADSBExchangeClient
from services.aviation.adsb_lol import ADSBLoLClient
from services.transport.osrm_routes import OSRMClient
from services.weather.noaa_nws import NOAAWeatherClient
from services.weather.ecmwf_grids import ECMWFGridStore
from services.sar.nasa_earthdata import NASAEarthdataClient
from services.sar.google_earth_engine import GoogleEarthEngineClient
from services.sar.copernicus_scihub import CopernicusSciHubClient
from services.photogrammetry.webodm_client import WebODMClient


async def _iniciar_tezcatlipoca(app: FastAPI) -> Optional[dict]:
    """Inicializa los engines/clientes de Tezcatlipoca y los expone en
    app.state -- lo que antes solo pasaba si se corría
    tezcatlipoca/main.py standalone. Devuelve el dict de objetos vivos
    (para poder cerrarlos ordenadamente en el shutdown) o None si algo
    falló. Envuelto en try/except a propósito: un problema inicializando
    OSINT (una API externa caída, un directorio sin permisos de
    escritura para SnapshotStore, lo que sea) NO debe tumbar el arranque
    de Megalodon completo -- expedientes/presupuestos/licitaciones no
    tienen nada que ver con que el módulo OSINT esté sano. Si falla, se
    loguea con traceback completo y los endpoints de Tezcatlipoca que
    dependen de app.state siguen devolviendo 500 (ni mejor ni peor que
    antes de este fix), pero el resto del sistema arranca normal."""
    app.state.tezcatlipoca_status = {"state": "STARTING", "reason": None}
    app.state.tezcatlipoca_components = {}
    # CORREGIDO (contra-auditoría V8, F-08 problema 2): antes, si algo
    # fallaba a mitad de esta función DESPUÉS de haber creado uno o más
    # clientes con sesión aiohttp propia, el except de abajo hacía
    # "return None" sin cerrar nada -- esos clientes ya creados quedaban
    # vivos indefinidamente (el shutdown normal nunca corre porque
    # _detener_tezcatlipoca(None) es un no-op). Ahora se va acumulando en
    # `parcial` cada recurso justo después de crearlo, y si algo truena,
    # el except cierra lo que alcanzó a existir con el mismo
    # _detener_tezcatlipoca() que ya usa el shutdown normal (cada cierre
    # ahí ya está envuelto en su propio try/except, así que es seguro
    # llamarlo con objetos a medio inicializar).
    parcial: dict = {"data_fetcher": None, "ais_connector": None, "clients_con_http_session": []}
    try:
        await init_db_async()

        data_fetcher = DataFetcherEngine()
        parcial["data_fetcher"] = data_fetcher
        peer_engine = MaxPowerPeerEngine(
            epsilon_dp=float(os.getenv("MESH_EPSILON_DP", "1.0")),
            stake_amount=int(os.getenv("MESH_STAKE_AMOUNT", "1000")),
            verification_rate=float(os.getenv("MESH_VERIFICATION_RATE", "0.02")),
            burn_in=int(os.getenv("MESH_BURN_IN", "50")),
        )
        honeypot_engine = HoneypotEngine(base_rate=0.03, adaptive_factor=2.0, covert_mode=True)
        sprt_slashing = SPRTSlashingFixed(p0=0.80, p1=0.20, alpha=0.01, beta=0.05)
        sovereign = SovereignShell(peer_engine, honeypot_engine, sprt_slashing)

        snapshot_store = SnapshotStore()
        cctv_pipeline = CCTVPipeline()
        parcial["clients_con_http_session"].append(cctv_pipeline)
        sigint_engine = SIGINTEngine()
        parcial["clients_con_http_session"].append(sigint_engine)
        sar_connector = SARConnector()
        parcial["clients_con_http_session"].append(sar_connector)
        ais_connector = AISConnector()
        parcial["ais_connector"] = ais_connector
        osint_engine = OSINTReconEngine()
        parcial["clients_con_http_session"].append(osint_engine)
        malware_aggregator = MalwareAggregator()
        data_fetcher.malware_aggregator = malware_aggregator
        parcial["clients_con_http_session"].append(malware_aggregator)

        data_fetcher.set_websocket_manager(ws_manager)
        await data_fetcher.start()
        await ais_connector.connect()

        graphhopper = GraphHopperClient()
        parcial["clients_con_http_session"].append(graphhopper)
        db_trains = DBTrainClient()
        parcial["clients_con_http_session"].append(db_trains)
        gtfs_mobility = GTFSMobilityClient()
        parcial["clients_con_http_session"].append(gtfs_mobility)
        faa_notams = FAANOTAMClient()
        parcial["clients_con_http_session"].append(faa_notams)
        avwx = AVWXClient()
        parcial["clients_con_http_session"].append(avwx)
        adsb_exchange = ADSBExchangeClient()
        parcial["clients_con_http_session"].append(adsb_exchange)
        adsb_lol = ADSBLoLClient()
        parcial["clients_con_http_session"].append(adsb_lol)
        osrm_routes = OSRMClient()
        parcial["clients_con_http_session"].append(osrm_routes)
        noaa_weather = NOAAWeatherClient()
        parcial["clients_con_http_session"].append(noaa_weather)
        nasa_earthdata = NASAEarthdataClient()
        parcial["clients_con_http_session"].append(nasa_earthdata)
        gee = GoogleEarthEngineClient()
        copernicus_scihub = CopernicusSciHubClient()
        parcial["clients_con_http_session"].append(copernicus_scihub)
        webodm = WebODMClient()
        parcial["clients_con_http_session"].append(webodm)

        app.state.honeypot_engine = honeypot_engine
        app.state.sprt_slashing = sprt_slashing
        app.state.peer_engine = peer_engine
        app.state.graphhopper = graphhopper
        app.state.db_trains = db_trains
        app.state.gtfs_mobility = gtfs_mobility
        app.state.faa_notams = faa_notams
        app.state.avwx = avwx
        app.state.adsb_exchange = adsb_exchange
        app.state.adsb_lol = adsb_lol
        app.state.osrm_routes = osrm_routes
        app.state.noaa_weather = noaa_weather
        app.state.ecmwf_grids = ECMWFGridStore()
        app.state.nasa_earthdata = nasa_earthdata
        app.state.gee = gee
        app.state.copernicus_scihub = copernicus_scihub
        app.state.webodm = webodm
        app.state.ais_connector = ais_connector
        app.state.sar_connector = sar_connector
        app.state.sigint_engine = sigint_engine
        app.state.cctv_pipeline = cctv_pipeline
        app.state.data_fetcher = data_fetcher
        app.state.snapshot_store = snapshot_store
        app.state.osint_engine = osint_engine
        app.state.malware_agg = malware_aggregator
        app.state.sovereign = sovereign
        # Estado operativo por capacidad. "READY" significa que el componente pudo
        # construirse y registrarse; "CONFIG_REQUIRED" significa que el adaptador existe
        # pero requiere credenciales/fuente externa para operar. Nunca se representa como
        # un dato ejecutado con éxito.
        env = os.environ
        def _capability(state: str, reason: str | None = None, dependency_health: str = "internal") -> dict:
            return {"status": state, "reason": reason, "dependency_health": dependency_health, "last_success": None}

        app.state.tezcatlipoca_components = {
            "geo": _capability("READY"),
            "aviation_open": _capability("READY", "ADSB.lol: adapter created, provider health requires a successful query."),
            "weather_open": _capability("READY", "NOAA/NWS: only supported US territories; ECMWF requires locally ingested GRIB."),
            "weather_global": _capability("CONFIGURED" if app.state.ecmwf_grids.root else "CONFIG_REQUIRED", None if app.state.ecmwf_grids.root else "Configure TEZCATLIPOCA_ECMWF_STORE with real ECMWF IFS grids."),
            "routing_self_hosted": _capability("CONFIGURED" if osrm_routes.base_url else "CONFIG_REQUIRED", None if osrm_routes.base_url else "Set TEZCATLIPOCA_OSRM_URL for own routing server."),
            "osint": _capability("READY"),
            "malware": _capability("READY"),
            "sar": _capability(
                "CONFIGURED" if any(env.get(k) for k in ("NASA_ED_USERNAME", "GEE_PROJECT_ID", "COPERNICUS_USERNAME")) else "CONFIG_REQUIRED",
                None if any(env.get(k) for k in ("NASA_ED_USERNAME", "GEE_PROJECT_ID", "COPERNICUS_USERNAME")) else "Fuente SAR requiere credenciales/configuración.",
                "external",
            ),
            "aviation": _capability(
                "CONFIGURED" if any(env.get(k) for k in ("OPENSKY_USER", "AVWX_API_KEY", "ADSBEXCHANGE_API_KEY")) else "CONFIG_REQUIRED",
                None if any(env.get(k) for k in ("OPENSKY_USER", "AVWX_API_KEY", "ADSBEXCHANGE_API_KEY")) else "Fuentes de aviación requieren credenciales/configuración.",
                "external",
            ),
            "transport": _capability(
                "CONFIGURED" if any(env.get(k) for k in ("GRAPHHOPPER_API_KEY", "GTFS_FEED_URL")) else "CONFIG_REQUIRED",
                None if any(env.get(k) for k in ("GRAPHHOPPER_API_KEY", "GTFS_FEED_URL")) else "Proveedor de transporte requiere configuración.",
                "external",
            ),
            "photogrammetry": _capability(
                "CONFIGURED" if env.get("WEBODM_URL") else "CONFIG_REQUIRED",
                None if env.get("WEBODM_URL") else "WebODM no configurado.",
                "external",
            ),
            "telemetry": _capability("READY"),
            "cyber": _capability("READY"),
        }
        configured_external = [v for v in app.state.tezcatlipoca_components.values() if v["dependency_health"] == "external"]
        degraded = any(v["status"] == "CONFIG_REQUIRED" for v in configured_external)
        app.state.tezcatlipoca_ready = True
        app.state.tezcatlipoca_status = {
            "state": "DEGRADED" if degraded else "READY",
            "reason": "Hay capacidades opcionales sin configurar." if degraded else None,
            "components": app.state.tezcatlipoca_components,
        }

        logger.info("tezcatlipoca_startup_ok", componentes=app.state.tezcatlipoca_components)
        return {
            "data_fetcher": data_fetcher,
            "ais_connector": ais_connector,
            "clients_con_http_session": parcial["clients_con_http_session"],
        }
    except Exception as exc:
        app.state.tezcatlipoca_ready = False
        app.state.tezcatlipoca_status = {"state": "FAILED", "reason": str(exc)}
        logger.error("tezcatlipoca_startup_failed", error=str(exc), exc_info=True)
        await _detener_tezcatlipoca(parcial)
        return None


async def _detener_tezcatlipoca(vivos: Optional[dict]) -> None:
    """Cierra ordenadamente lo que _iniciar_tezcatlipoca() dejó vivo.
    También envuelto en try/except: un error cerrando una sesión HTTP no
    debe impedir que el resto del shutdown (p.ej. engine.dispose() de
    Megalodon) se ejecute."""
    if not vivos:
        return
    try:
        await vivos["data_fetcher"].stop()
    except Exception as exc:
        logger.warning("tezcatlipoca_shutdown_data_fetcher_error", error=str(exc))
    try:
        await vivos["ais_connector"].disconnect()
    except Exception as exc:
        logger.warning("tezcatlipoca_shutdown_ais_error", error=str(exc))
    for cliente in vivos.get("clients_con_http_session", []):
        try:
            await cliente.close()
        except Exception as exc:
            logger.warning("tezcatlipoca_shutdown_client_close_error", error=str(exc))
    logger.info("tezcatlipoca_shutdown_ok")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación."""
    # ─── OpenTelemetry initialization ───────────────────────────────
    init_telemetry(
        app=app,
        sqlalchemy_engine=engine.sync_engine if hasattr(engine, "sync_engine") else None,
    )
    logger.info("telemetry_initialized", otel_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "default"))
    configure_logging()
    logger.info(
        "megalodon_startup",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )

    # BUG ORIGINAL: CREATE EXTENSION vivía aquí, en cada arranque. Eso es
    # provisioning de infraestructura, no inicialización de la app -- y
    # CREATE EXTENSION normalmente requiere privilegios de superusuario en
    # Postgres (salvo extensiones "trusted"). Un usuario de BD de mínimo
    # privilegio (lo correcto en producción) hace que el backend ni
    # siquiera arranque. Se movió a alembic/versions/0001_extensions.py;
    # lifespan solo inicializa lo que le corresponde (clientes, caches,
    # health checks), no administra permisos de base de datos.

    from scripts.verify_migrated_schema import verify
    from app.models.base import Base
    async with engine.connect() as connection:
        await connection.run_sync(verify, metadata_collection=(Base.metadata,))

    tezcatlipoca_vivos = await _iniciar_tezcatlipoca(app)

    yield

    await _detener_tezcatlipoca(tezcatlipoca_vivos)

    await engine.dispose()
    logger.info("megalodon_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend empresarial para gestión de obras públicas - LOPSRM, LAASSP, LFT",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # BUG ORIGINAL: `allow_origins=["*"] if dev else []`. En dev, "*" +
    # allow_credentials=True hace que Starlette refleje el Origin
    # entrante (obligatorio: los navegadores rechazan "*" literal junto
    # con credentials), lo que en la práctica acepta cualquier origen con
    # credenciales -- una superficie CSRF innecesaria. En producción, `[]`
    # bloquea TODO origen, así que ningún request autenticado desde el
    # navegador habría funcionado si el frontend vive en otro dominio que
    # el API (el caso normal de una SPA separada del backend). Se usa una
    # allowlist explícita y configurable (CORS_ALLOWED_ORIGINS).
    app.add_middleware(BrowserOriginCSRFMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SecurityHeadersMiddleware, production=settings.is_production)

    # PENDIENTE J (observabilidad): agregado DESPUÉS de CORS/GZip a
    # propósito -- en Starlette, cada add_middleware() envuelve por
    # FUERA a los anteriores, así que este queda como la capa más
    # externa. Eso hace que el request_id y el timing de las métricas
    # cubran el request completo (incluyendo lo que hacen CORS/GZip),
    # y que el header X-Request-ID de la respuesta salga siempre, aun
    # si algo dentro de CORS/GZip fallara. Ver app/core/observability.py.
    app.add_middleware(RequestContextMiddleware)

    @app.middleware("http")
    async def tezcatlipoca_runtime_guard(request: Request, call_next):
        if request.url.path.startswith("/api/tezcatlipoca/"):
            if not getattr(request.app.state, "tezcatlipoca_ready", False):
                status_info = getattr(request.app.state, "tezcatlipoca_status", {"state": "FAILED"})
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "TEZCATLIPOCA_UNAVAILABLE",
                        "message": "El subsistema Tezcatlipoca no está listo; no se ejecuta el router para evitar 500 por estado incompleto.",
                        "status": status_info,
                    },
                )
        return await call_next(request)

    @app.exception_handler(MegalodonException)
    async def megalodon_exception_handler(request: Request, exc: MegalodonException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR", "message": "Error interno del servidor"},
        )

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/api/tezcatlipoca/status")
    async def tezcatlipoca_status():
        """Estado operativo por capacidad, sin exponer secretos."""
        return getattr(
            app.state,
            "tezcatlipoca_status",
            {"state": "FAILED", "reason": "No inicializado", "components": {}},
        )

    @app.get("/ready")
    async def ready_check():
        db_ready = False
        redis_ready = True

        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ready = True
        except Exception:
            db_ready = False

        if settings.is_production or settings.security_protection_fail_closed:
            redis_ready = False
            try:
                redis_client = get_redis()
                if redis_client is not None:
                    await redis_client.connect()
                    redis_ready = redis_client.is_healthy()
            except Exception:
                redis_ready = False

        # Procurement/Core SaaS no depende de Tezcatlipoca para readiness.
        # Tezcatlipoca se reporta como dependencia opcional/degradada, pero
        # un fallo de OSINT/Geo no puede sacar del aire CostOS/Procurement.
        tez_ready = bool(getattr(app.state, "tezcatlipoca_ready", False))
        core_ready = db_ready and redis_ready
        payload = {
            "status": "ready" if core_ready else "not_ready",
            "database": db_ready,
            "redis": redis_ready,
            "tezcatlipoca": tez_ready,
            "tezcatlipoca_status": getattr(app.state, "tezcatlipoca_status", None),
            "optional_dependencies": {"tezcatlipoca": "ready" if tez_ready else "degraded"},
            "ready": core_ready,
        }
        return JSONResponse(payload, status_code=200 if core_ready else 503)

    # PENDIENTE J (observabilidad): scrape-able por Prometheus/Grafana
    # estándar -- sin decorator @app.get porque metrics_endpoint ya es
    # un handler ASGI-compatible reutilizable (ver app/core/observability.py).
    # Sin auth a propósito: es la convención habitual de /metrics (el
    # scraper vive en la red interna); si se expone fuera de esa red,
    # restringir por firewall/reverse-proxy, no aquí.
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)

    # API REST v1
    app.include_router(api_router, prefix="/api/v1")

    # ═══════════════════════════════════════════════════════════
    # INTEGRACIÓN ZIP 4: TEZCATLIPOCA -- renombrados bajo
    # /api/tezcatlipoca/* (NO son los mismos prefijos que traía en su
    # propio main.py, que eran planos: /api/aviation, /api/cyber, etc.
    # Se namespacearon a propósito para que no choquen ni se confundan
    # con /api/v1/* de Megalodon. Si algo externo ya le apunta a las
    # rutas planas originales de tezcatlipoca, hay que actualizarlo.
    # ═══════════════════════════════════════════════════════════
    app.include_router(tz_auth_router, prefix="/api/tezcatlipoca/auth", tags=["Tezcatlipoca: Auth"])
    app.include_router(tz_admin_router, tags=["Tezcatlipoca: Admin"])
    if settings.FEATURE_AI_ASSISTANT:
        app.include_router(tz_ai_router, prefix="/api/tezcatlipoca/ai", tags=["Tezcatlipoca: AI"])
    app.include_router(tz_cyber_router, prefix="/api/tezcatlipoca/cyber", tags=["Tezcatlipoca: Cyber"])
    app.include_router(tz_entity_router, prefix="/api/tezcatlipoca/entity", tags=["Tezcatlipoca: Entity"])
    app.include_router(tz_geo_router, prefix="/api/tezcatlipoca/geo", tags=["Tezcatlipoca: Geo"])
    app.include_router(tz_weather_router, prefix="/api/tezcatlipoca/weather", tags=["Tezcatlipoca: Weather"])
    app.include_router(tz_geo_threats_router, prefix="/api/tezcatlipoca/geo", tags=["Tezcatlipoca: Geo Threats"])
    app.include_router(tz_layers_router, prefix="/api/tezcatlipoca/layers", tags=["Tezcatlipoca: Layers"])
    app.include_router(tz_malware_router, prefix="/api/tezcatlipoca/malware", tags=["Tezcatlipoca: Malware"])
    app.include_router(tz_mesh_router, prefix="/api/tezcatlipoca/mesh", tags=["Tezcatlipoca: Mesh"])
    app.include_router(tz_osint_router, prefix="/api/tezcatlipoca/osint", tags=["Tezcatlipoca: OSINT"])
    app.include_router(tz_snapshots_router, prefix="/api/tezcatlipoca/snapshots", tags=["Tezcatlipoca: Snapshots"])
    app.include_router(tz_telemetry_router, prefix="/api/tezcatlipoca/telemetry", tags=["Tezcatlipoca: Telemetry"])
    app.include_router(tz_honeypot_router, prefix="/api/tezcatlipoca/honeypot", tags=["Tezcatlipoca: Honeypot"])
    app.include_router(tz_transport_router, prefix="/api/tezcatlipoca/transport", tags=["Tezcatlipoca: Transport"])
    app.include_router(tz_aviation_router, prefix="/api/tezcatlipoca/aviation", tags=["Tezcatlipoca: Aviation"])
    app.include_router(tz_sar_router, prefix="/api/tezcatlipoca/sar", tags=["Tezcatlipoca: SAR"])
    app.include_router(tz_photogrammetry_router, prefix="/api/tezcatlipoca/photogrammetry", tags=["Tezcatlipoca: Photogrammetry"])
    app.include_router(tz_scm_router, prefix="/api/tezcatlipoca/scm", tags=["Tezcatlipoca: SCM"])
    app.include_router(tz_settings_router, prefix="/api/tezcatlipoca/settings", tags=["Tezcatlipoca: Settings"])
    app.include_router(tz_wormhole_router, prefix="/api/tezcatlipoca/wormhole", tags=["Tezcatlipoca: Wormhole"])

    # WebSocket
    app.include_router(ws_router)

    return app


app = create_app()
