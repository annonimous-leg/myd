# Esqueleto de proposición (LEGAL / TÉCNICA / ECONÓMICA)

## Fuente de verdad
`backend/app/data/seeds/proposition_structure.csv` → motor
`backend/app/engines/procurement/proposition_structure.py`

## API
- `POST /procurement/derive-proposition-structure`
- `POST /procurement/economic-congruence-check`

## APU
Marcador `APU_DEFERRED_UNTIL_CATALOG_LOAD` en `ECO-APU`.
Catálogos de referencia exportados desde el frontend:
- `catalogo_conceptos_referencia.csv` (3 conceptos muestra)
- `catalogo_insumos_referencia.csv` (insumos MAT/MAN/EQ reales del repo)

Cuando entregues catálogos completos CFE/CMIC/CONAGUA/SCT → ETL a
`catalogo_fuentes` / `conceptos_catalogo` / `catalogos_apu` (modelos ya existen).

## Inventario precios ya en repo
Frontend `megalodon-costos/data/catalogo.ts`: precios unitarios de referencia
(concreto, cemento, arena, gravas, peón, oficial, revolvedora…). Son reales del
proyecto, no placeholders vacíos; validar vigencia antes de uso productivo.
