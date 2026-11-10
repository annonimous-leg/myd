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
