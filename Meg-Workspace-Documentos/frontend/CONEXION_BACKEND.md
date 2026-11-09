<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Conexión frontend ↔ backend — estado real

## Qué queda conectado de verdad

1. **`src/lib/megalodon-client.ts`** — el cliente corregido, copiado tal
   cual del backend (mismo archivo, ya verificado con `tsc`).
2. **`src/lib/api-client.ts`** (nuevo) — instancia única del cliente. URL
   configurable con `VITE_API_URL` (ver `.env.example`), default
   `localhost:8000`. Restaura el token guardado al recargar la página.
3. **`src/stores/useAuthStore.ts`** (reescrito) — `login(email, password)`
   ahora es async y llama de verdad a `/auth/login` + `/auth/me`. Antes:
   síncrono, aceptaba cualquier texto de 2+ caracteres como usuario válido
   y nunca tocaba el backend (el propio comentario del código decía "en
   producción esto irá contra el backend").
4. **`src/components/LoginScreen.tsx`** — el formulario ya tenía campo de
   contraseña (se capturaba pero se descartaba). Ahora se manda de verdad,
   con manejo de error real del backend (credenciales incorrectas, etc.)
   en vez del `setTimeout` que simulaba una carga falsa.
5. Se preservó el modo **"Invitado"** como `loginAsGuest()` — sigue sin
   tocar el backend, para poder explorar el sistema sin credenciales.
6. Se agregó `src/vite-env.d.ts`, que faltaba en el proyecto (sin él,
   `import.meta.env.VITE_API_URL` no compila con TypeScript — no es algo
   que haya introducido yo, ya faltaba).
7. **App nueva "Proyectos"** (`src/apps/proyectos/`) + `useExpedienteStore.ts`
   — lista expedientes reales del backend, permite crear uno nuevo (con
   los campos de clasificación archivística que el backend realmente
   exige: órgano, unidad administrativa, serie/subserie documental) y
   marcar cuál es el "activo". Registrada como app fija (pinned) en
   `useAppRegistry.ts`. El expediente activo se persiste en localStorage
   (solo el ID; la lista siempre se vuelve a pedir al backend al abrir).

## Por qué se hizo como app aparte y no un modal forzado

Se decidió explícitamente construir esto como una app real con selector
(no un atajo de "crear expediente automático") porque varios expedientes
por usuario es el caso normal en obra pública, no la excepción.
`useExpedienteStore().expedienteActivo()` es ahora la fuente única de
verdad que **megalodon-costos** y **bim-calculator** deben leer antes de
llamar a cualquier endpoint que pida `expediente_id`.

## Pendiente (siguiente paso natural)

- **`megalodon-costos/index.tsx` (BudgetGrid)** ✅ conectado: lee
  `useExpedienteStore().expedienteActivo()`, muestra aviso si no hay
  expediente activo, calcula con la misma fórmula real del backend
  (directo → indirecto 15% → utilidad 10% → IVA 16%, no el 16% plano que
  tenía antes), y tiene botón "Guardar en backend" que persiste de verdad
  vía `client.presupuestos.create()`. Limitación honesta: el detalle de un
  presupuesto ya guardado todavía no se puede volver a cargar en la
  rejilla para editarlo -- el endpoint actual no regresa las partidas
  anidadas, solo los totales. Es un pendiente real, no algo que se
  intentó ocultar.
- **`bim-calculator`** ✅ conectado: se agregó un modo "Modelo IFC" (el
  modo "Manual" original se conservó intacto) que sube el IFC real,
  muestra el resumen por tipo de elemento, y renderiza la malla en 3D con
  `@react-three/fiber` + `@react-three/drei` (ya estaban en el
  `package.json`, no se agregó ninguna dependencia nueva). Incluye botón
  "Generar presupuesto" que llama a `client.bim.generarPresupuesto()`.
- Los engines locales `validador.ts` / `montecarlo.ts` / `juridico.ts`
  dentro de `megalodon-costos/engines/` siguen calculando del lado del
  cliente — decidir cuáles conviene dejar así (cálculos ligeros) vs.
  cuáles deben ir contra las reglas reales del backend
  (`client.validadores.*` / `client.riesgo.*` / `client.juridico.*`).

## Actualización: los 3 engines locales, resueltos con arquitectura clara

- **Montecarlo**: se mantiene el cálculo local como "vista previa" (botón
  renombrado explícitamente), y se agregó "Simular oficial (backend)" que
  manda la simulación real a Celery (`client.riesgo.simular` +
  `consultar` con polling cada 2s) y muestra el resultado en una tarjeta
  aparte, claramente etiquetada como oficial. Nunca se mezclan los dos
  resultados.
- **Jurídico**: se eliminó la duplicación real que encontré al revisar --
  `evaluateLegalFramework` (local) YA determinaba su propio
  `procedureName` y `requirements`, compitiendo con lo que el backend
  decide. Ahora `ReportPanel` llama a
  `client.juridico.determinarProcedimiento()` y usa ESA respuesta
  (procedimiento + requisitos + observaciones) tanto en pantalla como en
  el reporte exportado. Solo `legal.recommendations` se dejó local, porque
  son sugerencias de redacción, no una determinación legal.
- **Validador**: se decidió NO conectarlo todavía. `validador.ts` (358
  líneas: RFC/SAT, IMSS, INFONAVIT, e.firma, FSR, maquinaria, indirectos)
  es más rico que el único endpoint del backend
  (`validadores.validarCompleto(rfc, fsr)`). Conectarlo tal cual sería un
  downgrade real de funcionalidad. Pendiente: portar los validadores
  reales de `megalodon_costos_v3_1.py` (los 9 `Validador*`) al backend
  primero -- ver ROADMAP.md, ya estaba anotado ahí antes de esta sesión.

