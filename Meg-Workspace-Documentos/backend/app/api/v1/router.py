# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Router principal API v1.
Incluye routers existentes + nuevos módulos Fase 2 + Integración ZIP 2 y 3.
"""
from fastapi import APIRouter
from app.api.v1 import catalogo_importaciones

from app.api.v1 import (
    auth, users, expedientes, presupuestos, bim, juridico,
    montecarlo, validadores, ocr, firma, programacion, topografia,
    dashboard, catalogo_apu, proveedores,
    compliance, transparencia, catalogo_conceptos, catalogo_libro,
    audit, documentos, search, expedientes_advanced, indices_costos,
    presupuestos_advanced, legal_consultor,
    # ═══ Entitlements / Pagos ═══
    entitlements, pagos, procurement,
)

api_router = APIRouter()

# The legacy contracting-authority lifecycle routers are intentionally not mounted.
# Their tables and rows remain in the schema for history and audit. The active
# bidder workflow lives in TenderPackage under /procurement and never publishes
# a call, receives competing offers, issues a fallo/adjudication or creates an
# official contract.

# ─── Routers base ─────────────────────────────────────────
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticación"])
api_router.include_router(expedientes.router, prefix="/expedientes", tags=["Expedientes"])
api_router.include_router(presupuestos.router, prefix="/presupuestos", tags=["Presupuestos"])
api_router.include_router(bim.router, prefix="/bim", tags=["BIM/IFC"])
api_router.include_router(juridico.router, prefix="/juridico", tags=["Jurídico"])
api_router.include_router(montecarlo.router, prefix="/riesgo", tags=["Riesgo / Monte Carlo"])
api_router.include_router(validadores.router, prefix="/validadores", tags=["Validadores"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["OCR / Metrados"])
api_router.include_router(firma.router, prefix="/firma", tags=["Firma Electrónica"])
api_router.include_router(programacion.router, prefix="/programacion", tags=["Programación de Obra"])
api_router.include_router(topografia.router, prefix="/topografia", tags=["Topografía"])

# NOTA: websocket.router NO se monta aquí. Sus @router.websocket(...) ya
# traen "/ws/progreso" y "/ws/notificaciones" como paths literales
# completos, así que montarlo aquí bajo prefix="/ws" (y api_router bajo
# "/api/v1") producía /api/v1/ws/ws/progreso -- una ruta que nadie llama.
# El frontend conecta a ws://host/ws/progreso (sin /api/v1), que es
# exactamente lo que main.py ya expone montando ws_router sin prefijo.
# Ver app/main.py.

# ─── Routers nuevos Fase 1 ─────────────────────────────────
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(catalogo_importaciones.router, prefix="/catalogo-apu", tags=["Importación de catálogos"])
api_router.include_router(catalogo_apu.router, prefix="/catalogo-apu", tags=["Catálogo APU"])
api_router.include_router(proveedores.router, prefix="/proveedores", tags=["Proveedores"])
api_router.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
api_router.include_router(transparencia.router, prefix="/transparencia", tags=["Transparencia"])
api_router.include_router(catalogo_conceptos.router, prefix="/catalogo-conceptos", tags=["Catálogos de Conceptos"])

# ─── Routers nuevos Fase 2 ─────────────────────────────────
api_router.include_router(audit.router, prefix="/audit", tags=["Auditoría"])
api_router.include_router(documentos.router, prefix="/documentos", tags=["Documentos / CDE"])
api_router.include_router(search.router, prefix="/search", tags=["Búsqueda"])
api_router.include_router(expedientes_advanced.router, prefix="/expedientes-advanced", tags=["Expedientes Avanzado"])
api_router.include_router(presupuestos_advanced.router, prefix="/presupuestos-advanced", tags=["Presupuestos Avanzado"])

# ═══════════════════════════════════════════════════════════════
# INTEGRACIÓN ZIP 3: LEGL CONSULTOR LEGAL
# ═══════════════════════════════════════════════════════════════
api_router.include_router(legal_consultor.router, prefix="/legal", tags=["Consultor Legal LEGL"])

# ═══════════════════════════════════════════════════════════════
# ENTITLEMENTS / PAGOS (freemium: Free/Intermedio/Pro/Enterprise)
# ═══════════════════════════════════════════════════════════════
api_router.include_router(entitlements.router, prefix="/entitlements", tags=["Entitlements"])
api_router.include_router(pagos.router, prefix="/pagos", tags=["Pagos"])

# Tender Automation Domain
api_router.include_router(procurement.router, prefix="/procurement", tags=["Tender Automation"])

api_router.include_router(catalogo_libro.router, prefix="/catalogo-libro", tags=["Catálogo del libro"])
api_router.include_router(indices_costos.router, prefix="/indices-costos", tags=["Índices de costos"])

api_router.include_router(users.router, prefix="/users", tags=["Usuarios"])
