# Costeo desde el catálogo privado

Documento operativo reconstruido durante la recuperación del 2026-09-30.

En Proyectos seleccionar un expediente; abrir Costos → Presupuesto → Catálogo del libro.
Buscar concepto y revisar modelo, página y supuesto; capturar cantidad de la obra y agregar.
Capturar explícitamente indirectos, utilidad, impuesto y referencia antes de guardar.
La rejilla muestra un estimado; el guardado confirma el resultado del backend.

El CSV no se publica en GitHub. Para ejecutarlo, colocar el archivo en
`backend/data/private/catalogo.csv` o establecer `CATALOGO_LIBRO_CSV` con una ruta absoluta.
En Docker montar ese archivo de solo lectura y pasar la variable al contenedor.
El ZIP privado de recuperación incluye el CSV en la primera ruta.

Sin archivo, la API responde 503; no usa datos de demostración.
`GET /api/v1/catalogo-libro?q=texto&skip=0&limit=50` requiere autenticación.
La creación de presupuesto admite `catalogo_libro_id` por partida. El servidor resuelve
precio, descripción y unidad y guarda la fila original y su hash en los metadatos.
Los porcentajes, filas sin unidad y filas marcadas para revisión quedan bloqueados.
No se inventa desglose, zona ni vigencia. La marca False del CSV no certifica su revisión visual.

Cabecera y partidas se guardan con un commit. Recalcular usa el precio persistido.
Las referencias de selección cambian cuando cambia el archivo; reiniciar los procesos tras
reemplazarlo. Las cantidades nuevas se calculan sin modificar el importe original del libro.

Instalación desde backend: `uv sync --frozen --extra dev`.
Pruebas: `uv run --frozen --extra dev pytest -q -rs`.
Con el archivo privado real: definir `MEGALODON_TEST_CATALOGO_REAL` al ejecutar pytest.
Frontend desde frontend/app: `npm ci`, `npm run build`, `npm audit`.

Los resultados históricos y las limitaciones de la recuperación están en CHECKPOINT.md.
Los locks se regeneraron después de la limpieza; no se afirma que sean idénticos a los
usados en las 307 pruebas históricas. Antes de desplegar, repetir pruebas y build.

Referencias técnicas consultadas durante la implementación:
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- https://docs.sqlalchemy.org/en/21/orm/session_transaction.html
- https://docs.python.org/3.14/library/decimal.html
