# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

# MEGALODON — SQLite Temporal para Desarrollo

## ⚠️ ADVERTENCIA: TEMPORAL PARA DESARROLLO

Este schema SQLite **NO ES PARA PRODUCCIÓN**. Es una base de datos temporal para:
- Desarrollo local rápido
- Pruebas de integración
- Demostraciones sin dependencia de PostgreSQL/Supabase
- Validación de modelos y relaciones antes de migrar a producción

**En producción se usa PostgreSQL + PostGIS en Supabase.**

## ¿Qué contiene?

### Schema completo (`sqlite_dev_schema.sql`)
Todas las tablas del scaffold v2.0 mapeadas a SQLite:
- Platform Core (tenants, users, entidades, proveedores)
- Catálogos Maestros (procedimientos, jurídico)
- Catálogos de Fuentes (CFE, CMIC, CONAGA, salarios, maquinaria)
- Expedientes + Planeación
- Documentos / CDE
- Licitaciones + Juntas de Aclaración + Proposiciones
- Contratos + Modificatorios + Garantías + Entregables
- Compliance (reglas, inconformidades, sanciones)
- Audit Ledger (bitácora inmutable)
- Workflow (transiciones, tareas)
- Presupuesto + Partidas + Conceptos + Insumos
- Catálogo APU interno
- BIM (modelos, elementos)
- Programación (programas, actividades)
- Topografía (levantamientos, puntos)
- Validadores

### Seed Data (`sqlite_seed_data.sql`)
Datos de muestra extraídos de **PDFs oficiales reales**:

| Fuente | Archivo PDF | Qué contiene |
|--------|-------------|-------------|
| **CFE 2026** | `1039183160-CATALOGO-DE-PRECIOS-UNITARIOS-CFE-2026.pdf` | Rehabilitación de pozos (CT7-XXXXX), servicios de sondaje (SR-XXXX). Precios **SIN IVA**. Zonas I, II, III. |
| **CMIC Pozos 2026** | `1030112820-Rehabilitacion-Pozos-2026.pdf` | Rehabilitación de pozos por diámetro (6"-10", 12"-16"). Urbano y Rural. Materiales, maquinaria y mano de obra detallada. |
| **CONAGA SGIH 2026** | `CAT_LOGO_POR_GERENCIA_SGIH_2026.pdf` | Conceptos por gerencia (Distrito Riego, Unidad Riego, Temporal Tecnificado). Código X.X.X.X. Unidades: m2, m3, km, Pza. Estados: Aguascalientes, Jalisco, Sinaloa. |
| **Salarios Profesionales** | Referencia mercado 2026 | Ingeniero residente, supervisor, topógrafo, arquitecto, jefe de obra, etc. |
| **Maquinaria y Equipo** | Referencia mercado 2026 | Excavadoras, grúas, camiones, bombas, compresores, generadores, sondas, etc. |
| **Materiales** | Referencia mercado 2026 | Cemento, acero, PVC, agregados, aditivos, sellos. |
| **Costos por m²/m³** | Referencia mercado 2026 | Muros, cimentación, losas, concreto por resistencia. |

## Cómo usar

```bash
# 1. Crear base de datos SQLite
cd backend/scripts
sqlite3 megalodon_dev.db < sqlite_dev_schema.sql

# 2. Cargar datos de muestra
sqlite3 megalodon_dev.db < sqlite_seed_data.sql

# 3. Verificar
sqlite3 megalodon_dev.db "SELECT COUNT(*) FROM conceptos_catalogo;"
# → 25 conceptos (partes de CFE, CMIC, CONAGA)

sqlite3 megalodon_dev.db "SELECT COUNT(*) FROM insumos_catalogo;"
# → 60 insumos (materiales, mano de obra, maquinaria, salarios, costos por m²/m³)
```

## Migración a PostgreSQL/Supabase (Producción)

```bash
# 1. Crear schema en Supabase (usando el mismo SQL adaptado)
# 2. ETL completo desde PDFs oficiales
# 3. Este SQLite se descarta — solo sirvió para desarrollo
```

## Notas
- Los precios son **SIN IVA** (como en los PDFs originales).
- Las zonas económicas varían por fuente: CFE usa Zona I/II/III; CMIC usa Urbano/Rural; CONAGA usa gerencia/estado.
- Los datos son **PARTES** de los catálogos, no el catálogo completo (los PDFs tienen miles de conceptos).
- El ETL completo cargará todo el catálogo a Supabase.
