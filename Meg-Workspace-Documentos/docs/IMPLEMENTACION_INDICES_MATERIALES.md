# Actualización reproducible de materiales

## Alcance verificable

Flujo de esta entrega: registrar series y niveles publicados; revisar una
correspondencia por insumo y tenant; consultar el precio derivado; incorporarlo
a un APU; guardar presupuesto; recalcular y exportar sin consultar revisiones
nuevas. Los precios originales no se sobrescriben. Ningún dato oficial se
precarga a partir de porcentajes anuales ni de archivos de simulación.

Sólo materiales, MXN y precios sin IVA: el motor aplica los impuestos del
presupuesto una vez. Salario real, maquinaria compuesta, conversión de divisas,
pronósticos y ajustes contractuales requieren modelos propios y quedan fuera
de esta operación. Las correspondencias son decisiones revisadas explícitas,
no búsquedas automáticas por similitud. Una referencia bibliográfica no acredita
que una serie haya sido cargada o contrastada.

## Diseño y referencias

- INEGI, [API del Banco de Indicadores](https://www.inegi.org.mx/servicios/api_indicadores.html):
  conservar identificador originario, metadatos y periodo observado. El token
  de acceso no se guarda en URLs de evidencia.
- Federal Reserve Bank of St. Louis,
  [periodos de tiempo real](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html):
  implementación operativa de datos revisables; fecha conocida/publicada y mes
  observado son dimensiones distintas. La edición utilizada se elige por ID,
  nunca por un valor mutable llamado «actual».
- [PostgreSQL: constraints](https://www.postgresql.org/docs/current/ddl-constraints.html):
  FK, unicidad y checks protegen las referencias incluso fuera de HTTP.
- [Python: Decimal](https://docs.python.org/3/library/decimal.html):
  cálculo decimal con contexto local y redondeo HALF_UP explícito a centavos.
- [SQLAlchemy: eventos de sesión](https://docs.sqlalchemy.org/en/20/orm/session_events.html):
  los eventos de mapper no interceptan actualizaciones masivas. La inmutabilidad
  de la evidencia se protege con triggers PostgreSQL, además de una API sin
  PATCH/DELETE. No se confunde version_id_col con historia de publicaciones.

Estas fuentes responden problemas diferentes; no son mediciones independientes
de inflación. La selección económica del índice se fundamenta en
`INVESTIGACION_INDICES_INSUMOS_2026-09-30.md`.

## Contratos

Cada nivel registra serie/version metodológica, mes (primer día), fecha de
publicación, URL sin credenciales, SHA-256 del documento y localizador verificable.
Sólo `NIVEL` positivo y finito. Se bloquean meses sin cerrar, publicaciones
futuras, series agregadas, periodos incompatibles y observaciones retiradas.

Una correspondencia captura el precio del insumo en ese momento, la fuente y
las condiciones originales, el mes base, ámbito y sustento de revisión. Los
administradores sólo crean correspondencias de su tenant. Sólo superadmin
publica niveles/series globales. Lecturas de correspondencias y cálculos se
filtran por tenant. Un retiro es un evento nuevo; bloquea usos nuevos y conserva
las estimaciones ya emitidas.

Precio = precio original × nivel destino / nivel base, calculado directamente
desde los niveles (no desde un factor redondeado). Los tres IDs son explícitos.
Una edición corregida se inserta con un ID nuevo. La instantánea del presupuesto
incluye valores, fuentes, meses, correspondencia, política de redondeo y hash.
Al reconstruir se compara con el precio persistido del insumo; una alteración
no se disimula recalculando contra el catálogo actual.

La moneda histórica desconocida queda `NULL`. `POST
/api/v1/indices-costos/acreditaciones-moneda` permite a superadmin acreditar una
fuente sin moneda mediante URL, SHA y localizador; conserva revisor y fecha.
No sustituye una moneda ya declarada ni convierte divisas. Las fuentes nuevas
pueden declarar moneda en su registro; sólo MXN se acepta en este cálculo.

Una transcripción incorrecta puede corregirse conservando el SHA del documento:
retirar su observación; registrar el mismo mes/serie/documento con
`sustituye_id` y `revision_captura` anterior + 1. Una observación sólo admite un
sucesor. No se necesita falsificar un hash para corregir la captura.

Las mutaciones del presupuesto bloquean el agregado y confirman detalles,
manifiesto y recálculo juntos. Listar y exportar mantienen bloqueo compartido
durante la carga del padre y los hijos. Las columnas de texto del XLSX se escriben como
texto literal; importes y cantidades siguen siendo numéricos.

## Operación

1. Aplicar `alembic upgrade head` y ejecutar `python -m scripts.verify_migrated_schema`.
2. Revisar fuente del catálogo, moneda, mes observado del precio y condiciones
   de IVA/entrega. Acreditar moneda desconocida sólo con evidencia verificable.
3. Superadmin registra `/indices-costos/series` y `/observaciones` con niveles
   de la misma metodología, periodo de referencia y región. La API requiere
   revisión humana: no descarga documentos ni demuestra por sí sola que su
   contenido coincide con una captura.
4. Administrador del tenant registra `/vinculos`, fundamentando la pertinencia
   material/familia y las condiciones del precio. El selector «Actualizar
   material» ofrece únicamente correspondencias y observaciones activas.
5. Elegir ediciones base/destino, confirmar precio y añadir material. Guardar
   revalida las referencias en servidor; un retiro posterior al cálculo previo
   puede impedir el guardado y exigir elegir una edición válida.

El CSV del libro contiene precios de conceptos: sólo se actualiza por componente
cuando exista un desglose APU acreditado. Este módulo no inventa desgloses ni
atribuye la inflación de un material a un concepto completo. No se precargaron
niveles ficticios. La activación de las series oficiales y revisión de catálogos
continúa como trabajo separado, junto con salarios y maquinaria.

## Validación prevista

API autenticada → cálculo de dos materiales con alza/baja distintas → presupuesto
→ revisión/retirada posterior → recálculo y XLSX reproducibles. Rechazos: tasas
anuales, valores no finitos, moneda/IVA/tipo incompatible, tenant ajeno, serie
distinta, base errónea, datos futuros y falta de evidencia. Migración real sobre
PostgreSQL y verificación de bloqueo UPDATE/DELETE, incluida escritura SQL.
