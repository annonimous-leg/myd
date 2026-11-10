# Tezcatlipoca — primera entrega de conectores abiertos y motores propios (2026-11-10)

**Estado:** trabajo en rama, sin certificación productiva. La licencia de un dato
y la disponibilidad comercial garantizada de una **API alojada** son asuntos
diferentes. Esta entrega no incorpora contratos pagados ni elimina conectores
históricos. La finalidad es evitar que esos servicios sean la dependencia
**predeterminada** del contexto geográfico y de rutas.

## Entregado en código

| Capacidad | Ruta / implementación | Estado comprobable |
| --- | --- | --- |
| Aviones por región | `/api/tezcatlipoca/geo/context`, `/geo/flights` y `services/aviation/adsb_lol.py` | Consulta local ADSB.lol. Si la región excede un círculo de 250 NM, `coverage_limited`, **no** mapa mundial ficticio. Datos ODbL con atribución. |
| Rutas por carretera | `/api/tezcatlipoca/transport/route` → `OSRMClient` | Motor de rutas autoalojable. Requiere `TEZCATLIPOCA_OSRM_URL` y una base OSM extraída/preprocesada por el operador. No incluye instalación ni importación de mapas en esta entrega. |
| Pronóstico por sitio | `/api/tezcatlipoca/weather/forecast?lat=...&lon=...` → NOAA/NWS | Consulta por coordenadas. Principalmente EE. UU.; fuera de cobertura devuelve estado explícito, no extrapolación global. |
| Catálogo Sentinel-1 | `/api/tezcatlipoca/sar/copernicus/search` → CDSE OData | Metadatos abiertos desde el catálogo vigente. No procesa ráster, deformaciones ni detecta anomalías. |
| Telemetría de fuentes | `DataFetcherEngine` | OpenSky, Open-Meteo público y OpenAQ v2 **no** se programan por defecto. Se conserva su código anterior para migraciones. |
| Pruebas | `tests/unit/test_tezcatlipoca_open_providers.py` | Respuestas sintéticas para geofiltros, unidades, fallo seguro, controles de origen y licencias. Aceptación externa desde CI: solo USGS y NOAA/NWS, no producción. |

**Atención:** Los endpoints históricos de proveedores de pago o con
restricciones aún existen. El flag `TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS`
permite a los flujos de geo y de rutas volver a ellos **solo si el operador
demuestra disponer de derechos comerciales**. Este flag no reemplaza un
inventario global de licencias ni bloquea todas las rutas heredadas.
No desplegar las rutas heredadas comercialmente sin auditoría por endpoint.

## Variables

```dotenv
# Por defecto: false. No introducir claves de APIs restringidas sin licencia.
TEZCATLIPOCA_ALLOW_RESTRICTED_PROVIDERS=false

# URL de una instalación OSRM propiedad del operador (no demo público).
# Construir los mapas por separado y exponerla en una red protegida.
TEZCATLIPOCA_OSRM_URL=http://osrm:5000

# Opcional: identificación pública del operador ante NOAA/NWS.
TEZCATLIPOCA_NWS_USER_AGENT=Megalodon-Tezcatlipoca (https://github.com/annonimous-leg/myd)
```

El motor OSRM del ejemplo usa perfil `driving`; aún no calcula isócronas,
perfiles peatonales o bicicletas. La API no responde con valores inventados.

## Matriz de licencia — validar antes de comercializar

- **ADSB.lol**: API y datos ODbL 1.0; acceso gratuito best-effort,
  restricciones de cuota, obligaciones de atribución y de base de datos.
  No equivalen a una licencia de capacidad garantizada.
  https://www.adsb.lol/docs/open-data/api y https://www.adsb.lol/request
- **OpenStreetMap**: datos ODbL; atribución y obligaciones de
  share-alike cuando corresponda. Se usan extractos propios, **no** los
  servidores públicos de tiles o routing para producción.
  https://www.openstreetmap.org/copyright
- **OSRM**: licencia BSD-2-Clause del motor; licencia de los datos OSM
  por separado. https://github.com/Project-OSRM/osrm-backend
- **NOAA/NWS**: API abierta sin coste por consulta, límites razonables;
  cobertura geográfica y disponibilidad externas.
  https://www.weather.gov/documentation/services-web-api
- **Copernicus**: la licencia abierta se aplica a **Sentinel**, no
  indiscriminadamente a todo producto o material del portal.
  https://dataspace.copernicus.eu/terms-and-conditions
- **ECMWF Open Data**: datos CC BY 4.0 compatibles con uso comercial;
  falta construir la ingesta, descodificación GRIB y consulta por celda.
  No se anuncia como entregado. https://www.ecmwf.int/en/forecasts/datasets/open-data
- **USGS Landsat / NASA Earthdata**: la selección e importación continua
  con permisos por conjunto sigue pendiente. No se atribuye a esta
  entrega ningún flujo de procesado ráster completo.

## Pendientes — no son capacidades entregadas

1. Ingestor ECMWF/GRIB autoalojado para **meteorología global**, versión,
   publicación, validez, rejilla, unidades y origen. Fuera de cobertura
   NWS, la API debe conservar el estado no disponible hasta integrarlo.
2. Pipeline propio Sentinel/Landsat: descarga autenticada donde aplique,
   cola durable, COG/STAC, metadatos, reproyección, mosaico e índices
   geoespaciales; sin vender búsqueda de catálogo como procesamiento.
3. Importación/actualización del grafo OSM y operaciones reproducibles
   del servicio OSRM, con cuotas y observabilidad; optimización multi-
   paradas, isócronas y movilidad quedan para motores independientes.
4. Inventario completo de permisos de cada endpoint heredado y guard
   global que impida llamadas a licencias no comerciales.
5. Datos marítimos abiertos históricos (NOAA AIS/EMODnet) como
   **datos históricos**, no equivalentes a AIS mundial en vivo.
6. Cobertura mundial ADS-B/AIS a través de fuentes y acuerdos compatibles,
   y opcionalmente receptores propios. **No se exige hardware al cliente**,
   y no se afirma cobertura mundial con un solo receptor.
7. Pruebas externas por proveedor, seguridad de producción, disponibilidad
   sostenida y aceptaciones con datos reales por región.

## Integridad Megalodon

No cambiar el catálogo de precios, las fuentes de mercado ni los trabajos
BIM para adaptar información geoespacial. Todos los datos externos deben
conservar proveedor, tiempo de observación, recepción, licencia y cobertura;
sin esos campos no deben mostrarse como señales verificadas en vivo.

## Ejecución reproducible del motor de rutas (OPCIONAL, no desplegado)

En `backend/data/osrm/` colocar un extracto OSM `region.osm.pbf`
obtenido bajo licencia compatible. El nombre `region` puede cambiarse; guardar
junto al expediente de la fuente: URL, licencia, fecha, límites geográficos y
hash SHA-256 del extracto. Los datos masivos están excluidos del repositorio.

```bash
cd Meg-Workspace-Documentos/backend
# Inspeccionar e instalar Docker; colocar data/osrm/region.osm.pbf.
bash scripts/prepare_osrm.sh region
# En entorno con variables de producción y control del despliegue:
OSRM_DATASET_BASENAME=region docker compose \
  -f docker-compose.prod.yml -f docker-compose.osrm.yml \
  --profile geospatial config
# No iniciar servicios de producción sin autorización.
```

La configuración `docker-compose.osrm.yml` ejecuta OSRM sin publicar su
puerto al host, dentro de la red del stack. El contenedor API recibe
`TEZCATLIPOCA_OSRM_URL=http://osrm:5000`. Si el grafo no está listo,
Tezcatlipoca devuelve error explícito; no cambia silenciosamente a proveedores
con restricciones comerciales. **La preparación y despliegue real del servicio
no se han ejecutado ni validado en esta PR.**

Fuente oficial del procedimiento:
https://github.com/Project-OSRM/osrm-backend#using-docker

## Segunda entrega — exploración terrestre y ECMWF autoalojado

Esta sección documenta código agregado tras la primera entrega; no significa
que haya sido desplegado en un servidor del usuario ni validado con datos
científicos de campo. La integración hereda la autenticación de Megalodon.

### Explorador terrestre

La pestaña **Tierra** del `TezcatlipocaHub` ahora ofrece:
- Mapa MapLibre con mosaicos públicos **NASA GIBS MODIS Terra** por fecha
  (resolución de contexto, no una ortofoto topográfica ni Street View).
- Coordenadas EPSG:4326, navegación por posición y selección de puntos.
- Capas observadas de USGS, ADS-B y AIS recibidas desde el backend,
  consultadas a demanda; estados de origen, disponibilidad y caché.
- Enlace al motor orbital 3D existente (separado; aún no hay transición
  cinematográfica entre ese motor y la vista terrestre).
- Guardado de una **vista** mediante `/api/tezcatlipoca/snapshots/create`.
  El snapshot está delimitado por usuario/tenant, conserva fechas,
  fuentes, recuentos y parámetros geográficos. **No** es captura de
  pantalla raster ni entrega documental del Workspace. No marca
  información como aprobada.

Para prevenir confusiones: una imagen NASA GIBS con fecha de ayer no es
satélite a nivel de calle casi en directo; un vuelo sin posición reciente
no se incluye en la capa como observación actual.

### Meteorología mundial mediante ECMWF Open Data

**Se implementó un lector geográfico de rejillas IFS locales**, con
licencia de datos CC BY 4.0, temperatura a 2 m y vector de viento a 10 m.
No se inventa un pronóstico cuando no hay datos ingestados. La capa
de meteorología de NOAA/NWS permanece independiente para áreas cubiertas.

Comando para preparar una **edición real de pronóstico** (servicio de ingesta
operado por quien despliegue, no ejecutado aún):

```bash
# Ejecutar en un entorno de ingestión con Python y dependencias opcionales:
python -m pip install eccodes ecmwf-opendata
python - <<'PY'
from ecmwf.opendata import Client
Client(source="ecmwf", model="ifs", resol="0p25").retrieve(
    type="fc", step=24, param=["2t", "10u", "10v"], target="ifs.grib2"
)
PY
python scripts/ingest_ecmwf_open_data.py \
  --grib ./ifs.grib2 --store ./data/ecmwf

# En el servidor del API, solo el almacén procesado, montado read-only:
TEZCATLIPOCA_ECMWF_STORE=/run/megalodon/ecmwf
```

Endpoint autenticado:
`GET /api/tezcatlipoca/weather/global?lat=19.4326&lon=-99.1332`

Devuelve estado `config_required` si no se ha procesado un GRIB;
`unavailable` para archivos corruptos o checksums inválidos;
`stale` si el modelo lleva más de 36 horas sin actualizarse;
`out_of_coverage` donde el producto no cubre la coordenada.
En casos disponibles devuelve **un único paso de pronóstico**
de una versión inmutable, los metadatos ECMWF y conversión Kelvin/°C
y viento vectorial en m/s. No promete una serie horaria ni telemetría
observada en directo. El operador debe programar descargas y ventanas
de publicación antes de considerarlo operativo.

El ingestor acepta solo una rejilla global regular por paso,
con los tres campos necesarios y compatibilidad espacial.
Rechaza entradas demasiado grandes o heterogéneas, conserva el
SHA-256 del archivo fuente, guarda matrices NumPy por versión y publica
un puntero atómico `active.json`.

El store es independiente del repositorio: `backend/data/ecmwf/` está
excluido de Git. El despliegue opcional `docker-compose.ecmwf.yml`
monta el store como solo lectura. Este compose **no** descarga datos
automáticamente ni instala las dependencias científicas opcionales
en el contenedor API.

Fuentes y licencias:
- https://www.ecmwf.int/en/forecasts/datasets/open-data
- https://github.com/ecmwf/ecmwf-opendata
- https://sites.ecmwf.int/docs/eccodes/
- https://gibs.earthdata.nasa.gov/
- https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance

### Trabajo que sigue pendiente

- Automatizar ingesta ECMWF de varios pasos con scheduler durable,
  retención y métricas de cumplimiento, sin exceder cuotas.
- Integrar **procesado SAR/óptico** real: ráster COG, ortorrectificación,
  NDVI, mediciones de deformación solo con datos apropiados.
- Construir navegación orbital → superficie en el mismo mundo 3D y
  georreferenciación IFC con confirmación humana; no marcar cambios de
  geometría como aprobados automáticamente.
- Transferencia de evidencias al expediente Workspace, versionado,
  contenido y permisos. Guardar un snapshot de Tezcatlipoca **no** crea
  automáticamente un documento del expediente.
- Validar requisitos legales de redistribución de imágenes concretas,
  uso de geocodificación y un inventario de licencias de APIs heredadas.
