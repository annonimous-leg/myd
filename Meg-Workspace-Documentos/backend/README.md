Copyright © 2026 Cristian Rodriguez
All rights reserved.
Unauthorized copying, modification, distribution, or use is prohibited
without prior written permission.

# Megalodon CostOS v4 - Backend

Backend empresarial para gestión de obras públicas conforme a LOPSRM, LAASSP, LFT y CFF.

## Arquitectura

```
app/
├── api/v1/          # FastAPI routers
├── core/            # Dominio puro (constantes, errores, calendario)
├── engines/         # Motores de negocio
│   ├── costos/      # Motor de costeo y presupuestos
│   ├── bim/         # Motor BIM/IFC
│   ├── juridico/    # Motor jurídico
│   ├── programacion/# Programación de obra
│   ├── topografia/  # Topografía y GIS
│   ├── validadores/ # SAT, IMSS, INFONAVIT
│   ├── riesgo/      # Monte Carlo
│   └── ia/          # Inteligencia artificial (reservado)
├── models/          # SQLAlchemy 2.0 + PostGIS
├── schemas/         # Pydantic v2
├── services/        # Casos de uso
├── workers/         # Celery tasks
└── utils/           # Utilidades
```

## Inicio rápido

```bash
# 1. Clonar y entrar
cd megalodon-backend

# 2. Variables de entorno
cp .env.example .env

# 3. Levantar infraestructura
docker-compose up -d db redis minio

# 4. Instalar dependencias
pip install -e ".[dev]"

# 5. Migraciones
alembic upgrade head

# 6. Iniciar API
uvicorn app.main:app --reload

# 7. Iniciar worker (en otra terminal)
celery -A app.workers.celery_app worker --loglevel=info

# 8. Publicar y recuperar trabajos guardados (otra terminal)
python -m app.workers.job_dispatcher
```

El flujo BIM necesita API, worker y publicador activos. Los trabajos quedan en
PostgreSQL; el publicador vuelve a enviarlos cuando Redis se recupera. El
almacenamiento `filesystem` guarda IFC reales en `storage/bim` para pruebas
locales/staging. En producción configura `BIM_STORAGE_PROVIDER=supabase` y las
credenciales del almacenamiento. Conserva juntos el respaldo de PostgreSQL y
los archivos originales para poder recuperar una obra.

## Documentación API

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI: http://localhost:8000/openapi.json

## Tests

```bash
pytest tests/ -v --cov=app
```

## Licencia

MIT
