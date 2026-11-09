<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Roadmap Megalodon Backend — priorizado

Basado en tu listado completo de 24 puntos. Aquí solo el orden realista con
status, para no perder nada. Los puntos de arquitectura "algún día" (billing,
superadmin, Elasticsearch, blockchain, CI/CD completo) se dejan al final a
propósito: son válidos para una plataforma comercial madura, pero no bloquean
que el sistema funcione hoy.

## Hecho en esta sesión
- [x] Unificar sobre una sola base de backend (`programacion4`, la más
      completa y reciente de los 4 encontrados)
- [x] Backend arranca sin ImportError (engine/sesión centralizados)
- [x] Auth real conectado a DB (login, register, refresh, /me)
- [x] Motor de costos: bugs de cálculo corregidos (multi-concepto, recalcular,
      excel, sobrecostos, factor_riesgo)
- [x] Cliente TypeScript corregido y verificado con `tsc` (login, OCR,
      websocket, tipos de presupuestos)
- [x] Motor BIM/IFC real con `ifcopenshell` (cuantificación + malla para
      renderizar) — ver BIM_IFC_IMPLEMENTADO.md
- [x] Storage real con Supabase (BIM + documentos) — ver STORAGE_SUPABASE.md.
      Cierra 2 stubs reales: `subir_documento` no subía nada,
      `descargar_documento` regresaba siempre bytes vacíos.
- [x] `client.programacion` — el motor CPM/PERT/EVM (632 líneas, ya
      bastante completo) nunca tuvo namespace en el cliente TS. Se agregó
      completo (crear, listar, obtener, cpm, pert, evm, avance, gantt,
      curva-s, ruta-crítica) y de paso se corrigió el mismo riesgo de
      DetachedInstanceError que ya se había arreglado en presupuestos
      (`crear_programa`/`listar_programas`/`actualizar_avance` regresaban
      el ORM crudo sin response_model).
- [x] **Validadores reales** — los 10 validadores de
      `megalodon_costos_v3_1.py` (SAT32D, SeguridadSocial,
      FirmaElectronica, FactorSalarioReal, CostosHorariosMaquinaria,
      Sobrecostos, CongruenciaTemporal, GarantiaCumplimiento,
      PublicacionSIRECO, RequisitosParticipacion) portados fielmente,
      con el orquestador `MotorDeterministaLicitaciones` (incluye la
      regla de "primer FALLA crítico descalifica y detiene la
      evaluación", preservada tal cual del original). Antes: "validar" un
      RFC era checar que midiera 12-13 caracteres, sin tocar ninguna regla
      real. Nuevo endpoint `/validadores/{expediente_id}/evaluar-completo`
      + persistencia en `ValidacionPropuesta` (bitácora completa para
      auditoría, algo que no existía). El endpoint viejo `/completo` se
      conservó por compatibilidad pero ahora es honesto: dice
      explícitamente que solo es formato de RFC, no consulta real.
- [x] **Firma electrónica integrada** — se integró selectivamente
      `megalodon_production` (e.firma) como módulo interno, sin romper lo
      que ya funcionaba:
      - `app/modules/firma/pades_lt.py` (nuevo): firma PAdES-LT/LTA real
        con sello de tiempo RFC 3161 desde TSA pública real (antes:
        `generar_sello_tiempo()` era un placeholder que regresaba la hora
        actual, no un sello real).
      - `app/modules/firma/cfdi40.py` (nuevo): sellado digital de CFDI 4.0
        (Anexo 20 SAT) -- capacidad que no existía en absoluto. Deja claro
        que esto NO timbra (el timbrado requiere un PAC autorizado).
      - `app/modules/firma/plataformas.py` (nuevo): tabla de qué formato
        de firma (XAdES-EPES/PAdES-basic/PAdES-LT) exige cada plataforma
        gubernamental (CompraNet, IMSS, INFONAVIT, CFE, PEMEX...) por
        tipo de documento.
      - **`firma_service.py` reescrito** -- este era el bug más grave
        encontrado en todo el backend: `firmar_documento()` hacía
        `pdf_bytes = b""` (placeholder) y el resultado firmado nunca se
        guardaba (`# TODO: Subir a S3/MinIO`). Es decir, ningún documento
        se había firmado nunca de verdad. Ahora descarga el documento
        real de Supabase Storage, lo descifra si aplica, lo firma de
        verdad, y sube el PDF firmado de vuelta sin pisar el original.
      - NO se portó `megalodon_efirma_core.py` completo (988 líneas,
        mucho es UX de wizard/multi-plataforma cliente) ni
        `megalodon_efirma_server.py` (sería un segundo backend, prohibido
        por la especificación) -- se tomó solo lo que aporta al backend
        real sin duplicar lo que ya funcionaba en `firma_electronica.py`.
- [x] **BIM mejorado**: `nivel` (piso real vía IfcBuildingStorey) y
      `bbox` por elemento; visor con selector de nivel, color por tipo,
      selección con panel de detalle, toggle vista 3D/planta 2D
      (ortográfica), wireframe, auto-encuadre de cámara.
- [x] **Topografía, de 0 a nivel BIM** — ver TOPOGRAFIA_IMPLEMENTADO.md.
      TIN real (Delaunay), volúmenes corte/terraplén (método de área
      promedio por triángulo), curvas de nivel, perfiles longitudinales,
      geodesia (transformación CRS, cierre de poligonal), importador CSV
      PENZD, app nueva con visor 3D coloreado por elevación y calculadora
      de volumen -> presupuesto de movimiento de tierras. Se corrigió de
      paso que `Levantamiento` no tenía `expediente_id` (quedaba huérfano).
- [x] **Clash detection real** — ver CLASH_DETECTION_IMPLEMENTADO.md.
      Broad phase (árbol AABB estático) + narrow phase (Möller-Trumbore
      triángulo-triángulo real, no solo bounding box). NO terminó siendo
      un port directo de `dynamic_tree.c`/`mesh_contact.c` -- la lectura
      completa mostró que el primero es un árbol dinámico para cuerpos
      en movimiento (peso muerto para elementos BIM estáticos) y el
      segundo nunca colisiona malla-contra-malla (siempre mesh vs
      primitiva convexa). Se documentó el hallazgo y se construyó lo que
      el clash BIM realmente necesita, con algoritmos públicos estándar
      verificados con 3 suites de pruebas reales (no solo `py_compile`).
      De paso se corrigió que `alembic/env.py` no importaba
      `bim.py`/`validador.py` -- esas tablas nunca hubieran aparecido en
      un autogenerate.

## Siguiente (recomendado, en este orden)
1. **Conectar frontend ↔ backend real** — hoy MegalodonOS sigue 100% en
   cliente. Ya con auth, costos, BIM y storage reales, este es el
   siguiente paso natural.
2. **Mover procesamiento IFC a Celery** — ahora que el storage real ya
   existe, un worker puede descargar de Supabase, procesar pesado, y
   reportar progreso por websocket en vez de bloquear el request. Aplica
   también a clash detection en modelos grandes (ver
   CLASH_DETECTION_IMPLEMENTADO.md, pendiente de async).
3. **Reglas de exclusión de clash por tipo de par** (ej. columna vs
   cimentación, esperado que se toquen) -- siguiente paso natural de
   clash detection si el ruido de falsos positivos resulta un problema
   en modelos reales.
4. **Programación de obra**: ya tiene CPM/PERT/EVM/Gantt razonablemente
   completos (632 líneas) — falta exponerlos en el cliente TS (hoy no
   existe `client.programacion`, y el backend ya lo soporta).
5. **Validadores reales** (SAT/IMSS/INFONAVIT): hoy 85 líneas vs 9
   validadores reales en tu script original. Definir cuáles necesitan
   consumo de servicios externos reales vs. cuáles son solo reglas locales.
6. **Jurídico**: portar `MotorJuridico` con jurisdicciones (hoy 143 líneas).
7. **Topografía**: es lo más incompleto (0 líneas reales). Triangulación,
   TIN, volúmenes, geodesia — proyecto en sí mismo.
8. **Firma electrónica**: TSA, LTV, Merkle — ya hay una base (`ServicioFirma`)
   pero falta cerrar el flujo documental completo.
9. **Tests**: no hay ninguno todavía. Al menos unit tests del motor de
   costeo (es el más crítico, es dinero real).

## Más adelante (arquitectura de plataforma madura)
- Workflow/aprobaciones, notificaciones, audit/event bus, search/indexación
- Interoperabilidad formal (CFDI/SAT XML, CompraNet, GeoJSON/DXF)
- Comercial: usuarios, suscripciones, planes, pagos, cuotas, superadmin
- Observabilidad, CI/CD, secret management, hardening de seguridad
- Blockchain anchoring / TSA formal para firma (decidir estrategia primero)

## Nota sobre `megalodon-backend_repaired`
Esta rama (arquitectura distinta, `src/` en vez de `app/`) tiene módulos que
`programacion4` no tiene: licitaciones, blockchain, notificaciones, reportes.
Quedó pendiente tu decisión de portarlos — no se tocó en esta sesión.
