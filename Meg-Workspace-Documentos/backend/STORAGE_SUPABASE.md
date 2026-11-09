<!--
Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.
-->

# Storage real con Supabase — qué se conectó

## Qué se construyó

1. **`app/integrations/supabase_storage.py`** (nuevo) — wrapper delgado
   sobre `supabase-py` (`acreate_client`, cliente async oficial). Usa la
   **service role key**, no login de usuario final: el backend ya es la
   única fuente de verdad de autenticación (spec, sección 5.4), Supabase
   aquí es solo infraestructura de storage. Un cliente compartido
   (singleton) es seguro porque nunca se usa sesión de usuario final en
   él — cada llamada opera como la misma identidad de servicio.
2. **`app/config.py`** — nuevas variables `SUPABASE_URL`,
   `SUPABASE_SERVICE_KEY`, y un bucket por dominio (`bim-modelos`,
   `documentos`, `exportaciones`). Las variables viejas de S3/MinIO se
   dejaron como legado/opcional, documentadas como tal.
3. **`bim_service.py`** — `crear_modelo` ahora sí sube el IFC a
   Supabase (antes solo guardaba el *nombre* del archivo, nunca lo subía
   a ningún lado). Nuevo método `url_descarga_modelo` para bajar el
   original vía URL firmada.
4. **`documento_service.py`** — dos bugs reales cerrados:
   - `subir_documento` tenía `if self.storage: # TODO ... pass` — nunca
     subía nada, aunque el registro en BD sí se creaba (quedaba apuntando
     a un archivo que jamás existió en ningún lado).
   - `descargar_documento` regresaba `contenido = b""` **siempre** — un
     stub que ni siquiera intentaba tocar storage. Cualquier descarga daba
     un archivo vacío garantizado. Esto violaba directamente la regla de
     tu especificación ("prohibido dejar stubs sin cerrar en rutas que el
     usuario pueda alcanzar").
   - También se agregó el endpoint de descarga que faltaba en
     `app/api/v1/expedientes.py` (el método del servicio no tenía quién
     lo llamara desde la API).
5. **Cliente TS**: `expedientes.descargarDocumento`, `bim.descargarModeloUrl`.

## Decisión de diseño: qué se guarda en BD

Se guarda el **path dentro del bucket** (ej.
`expedientes/<id>/<uuid>_plano.pdf`), nunca una URL firmada — las URLs
firmadas expiran (por default 1 hora) y guardar una en BD la volvería
inválida pronto. La URL se genera al vuelo cuando alguien pide descargar.

## Lo que NO se pudo verificar (honestidad sobre los límites del sandbox)

Este entorno no tiene acceso a red, así que no se pudo instalar
`supabase-py` ni probar contra un proyecto Supabase real. Se verificó
sintaxis (`py_compile`) y se basó la implementación en la documentación
oficial vigente de `supabase-py` (cliente async `acreate_client`, métodos
`.storage.from_(bucket).upload/download/remove/create_signed_url`). Un
punto específico marcado en el código (`_extraer_signed_url`): el shape
exacto de la respuesta de `create_signed_url` ha variado entre versiones
de la librería (a veces `signedURL`, a veces `signedUrl`). Se maneja de
forma defensiva, pero **verifícalo la primera vez que lo corras** — si no
aparece la URL, imprime la respuesta cruda y ajusta esa función.

## Antes de usarlo en Railway

1. Crear los 3 buckets en el dashboard de Supabase: `bim-modelos`,
   `documentos`, `exportaciones` (privados, no públicos).
2. Copiar la **service role key** (Project Settings → API) a
   `SUPABASE_SERVICE_KEY` — nunca la `anon key`, esa no tiene permisos de
   escritura en buckets privados.
3. `pip install supabase` (ya está en `pyproject.toml`).

## Pendiente real (no se inventó nada para taparlo)

- El procesamiento de IFC sigue siendo síncrono en el request (ver
  BIM_IFC_IMPLEMENTADO.md) — ahora que el storage real ya existe, la
  siguiente pieza natural es mover el procesamiento pesado a un worker de
  Celery que descargue de Supabase, procese, y reporte progreso por
  websocket.
- Reportes/exportaciones (`storage_exportaciones()`) está definido pero
  todavía nadie lo usa — el Excel de presupuestos hoy se genera y regresa
  directo en la respuesta HTTP, no se persiste. Es una decisión válida
  para v1 (no todo necesita persistirse), pero queda como opción abierta.
