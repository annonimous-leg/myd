# 🛰️ TU-OSINT-PLATFORM v2.3.5

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-green)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev)
[![Three.js](https://img.shields.io/badge/Three.js-r170-black)](https://threejs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

> **Plataforma de Inteligencia de Fuentes Abiertas (OSINT) Geoespacial**
> 
> Dashboard de inteligencia que agrega 60+ fuentes de datos en tiempo real con visualización en mapa interactivo y sistema solar 3D.

---

## 📑 Tabla de Contenidos

- [Arquitectura](#-arquitectura)
- [Características](#-características)
- [Stack Tecnológico](#-stack-tecnológico)
- [Instalación Rápida](#-instalación-rápida)
- [Configuración](#-configuración)
- [Deployment](#-deployment)
- [Seguridad](#-seguridad)
- [Testing](#-testing)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Contribuir](#-contribuir)
- [Licencia](#-licencia)

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTE                              │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ React OSINT │  │  Solar Geo 3D   │  │  Admin Panel    │  │
│  │  Dashboard  │  │  (Three.js)     │  │  (full/admin)   │  │
│  └──────┬──────┘  └─────────────────┘  └─────────────────┘  │
└─────────┼─────────────────────────────────────────────────────┘
          │ HTTPS (443)
          ▼
┌─────────────────────────────────────────────────────────────┐
│                      NGINX (Reverse Proxy)                  │
│  • SSL Termination    • Rate Limiting    • Security Headers │
│  • CSP, HSTS, X-Frame    • Load Balancing                   │
└─────────┬───────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (8000)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Auth      │  │   Routers   │  │     Services        │  │
│  │  JWT+HTTP   │  │  20+ APIs   │  │  60+ OSINT Sources  │  │
│  │  Only Cookie│  │  Protected  │  │  External APIs      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Rate Limit  │  │   Audit     │  │   Mesh Governance   │  │
│  │ Middleware  │  │   Logging   │  │  Honeypot/SPRT      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────┬────────────────────────────┬────────────────────────┘
          │                            │
          ▼                            ▼
┌─────────────────┐          ┌─────────────────┐
│   PostgreSQL    │          │      Redis      │
│  Users/Sessions │          │  Cache/Blacklist│
│  Snapshots/Logs │          │  Rate Limiting  │
└─────────────────┘          └─────────────────┘
```

---

## ✨ Características

### 🌍 Inteligencia Geoespacial (60+ Fuentes)
| Categoría | Fuentes |
|-----------|---------|
| **Aviación** | ADS-B Exchange, OpenSky, AVWX, FAA NOTAMs |
| **Marítimo** | AIS Stream (barcos, pesqueros, portacontenedores) |
| **Terrestre** | DB Bahn, GraphHopper, GTFS |
| **Geofísico** | USGS Terremotos, Volcanes, Open-Meteo |
| **Ciberinteligencia** | Shodan, Censys, GreyNoise, CISA KEV, Feodo, URLhaus |
| **SAR** | Copernicus, NASA Earthdata, Google Earth Engine |
| **SIGINT** | KiwiSDR, SatNOGS, APRS |
| **OSINT Recon** | Whois, DNS, IP/Domain/Email lookup |
| **Fotogrametría** | WebODM Integration |

### 🔐 Seguridad Avanzada
- ✅ JWT con cookies **httpOnly** + **SameSite=Strict** + **Secure**
- ✅ Role-based access control (`restricted` → `full` → `admin`)
- ✅ Rate limiting global (100 req/min) + Nginx (10r/m auth)
- ✅ Session tracking en base de datos (IP, User-Agent, expiración)
- ✅ Token revocation (blacklist en Redis + PostgreSQL)
- ✅ Path traversal protection en uploads
- ✅ SSL verification en todas las requests externas
- ✅ Audit logging completo (quién, qué, cuándo, desde dónde)

### 🕸️ Mesh Governance
- Honeypot injection con SPRT (Sequential Probability Ratio Test)
- Max Power Peer consensus
- Sovereign Shell (gobernanza descentralizada)
- Slashing de nodos maliciosos

### 🚀 Blindaje de APIs Externas
- User-Agent rotativo con identificación del proyecto
- Jitter aleatorio (1-3s) entre requests
- Backoff exponencial en 429/5xx
- TTL de caché agresivo (2h-6h según fuente)
- WireGuard VPN opcional para ocultar IP real

---

## 🛠️ Stack Tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Backend | Python + FastAPI | 3.11 / 0.104.1 |
| Frontend OSINT | React + TypeScript + Vite | 18 / 5.0 |
| Frontend Solar | Three.js + GLSL Shaders | r170 |
| Mapas | MapLibre GL | 4.0 |
| Base de Datos | PostgreSQL (prod) / SQLite (dev) | 16.1 |
| Cache | Redis | 7.2 |
| Auth | JWT + bcrypt | PyJWT 2.8 |
| Container | Docker + Docker Compose | — |
| Proxy | Nginx | 1.25.3 |
| VPN | WireGuard | — |
| Testing | pytest + TestClient | — |

---

## ⚡ Instalación Rápida

### Requisitos
- Python 3.11+
- Node.js 18+ (para frontend)
- Docker + Docker Compose (opcional, recomendado para prod)
- Redis (opcional, recomendado para prod)

### 1. Clonar y entrar
```bash
git clone https://github.com/ytpremiumcr7-collab/Ost.git
cd Ost/TU-OSINT-BACKEND
```

### 2. Configurar entorno
```bash
cp .env.example .env
# Editar .env con tus secrets
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Inicializar base de datos
```bash
python -c "from db.models import init_db; init_db()"
```

### 5. Ejecutar tests
```bash
python -m pytest tests/ -v
```

### 6. Iniciar backend
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Iniciar frontend (en otra terminal)
```bash
cd frontend
npm install
npm run dev
```

---

## ⚙️ Configuración

### Variables de Entorno Esenciales

```bash
# ─── Seguridad ───
JWT_SECRET_KEY=change-this-in-production-min-32-chars-long
AGENT_HMAC_SECRET=change-this-too
API_KEY_MASTER=your-master-api-key

# ─── Base de Datos ───
DATABASE_URL=sqlite:///./osint_platform.db          # Dev
# DATABASE_URL=postgresql://user:pass@localhost/osint_db  # Prod

# ─── Redis ───
REDIS_URL=redis://localhost:6379/0

# ─── CORS ───
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# ─── Cookies ───
COOKIE_SECURE=false        # true en producción (requiere HTTPS)
COOKIE_DOMAIN=             # tu-dominio.com

# ─── Rate Limiting ───
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60

# ─── Secure Requests ───
REQUEST_USER_AGENT=TU-OSINT-Platform/2.3.5 (Research; security@example.com)
REQUEST_TIMEOUT=30
REQUEST_MAX_RETRIES=3
REQUEST_JITTER_MIN=1.0
REQUEST_JITTER_MAX=3.0

# ─── Cache TTLs ───
CACHE_TTL_MALWARE=7200
CACHE_TTL_CISA_KEV=21600
CACHE_TTL_OSINT=3600

# ─── External API Keys ───
SHODAN_API_KEY=
CENSYS_API_ID=
CENSYS_API_SECRET=
GREYNOISE_API_KEY=
OPENSKY_USER=
OPENSKY_PASS=
ADSBEXCHANGE_API_KEY=
AVWX_API_KEY=
NASA_USERNAME=
NASA_PASSWORD=
COPERNICUS_USER=
COPERNICUS_PASS=
GRAPHHOPPER_API_KEY=
WEBODM_URL=http://localhost:8000
WEBODM_TOKEN=

# ─── Deployment ───
ENVIRONMENT=development    # development | production
LOG_LEVEL=INFO
LOG_FILE=/var/log/tu-osint/app.log

# ─── Sentry (opcional) ───
# SENTRY_DSN=https://xxx@yyy.ingest.sentry.io/zzz
```

---

## 🚀 Deployment

### Docker Compose (Recomendado para Producción)

```bash
cd TU-OSINT-BACKEND

# 1. Configurar producción
cp .env.example .env
# Editar .env:
#   ENVIRONMENT=production
#   COOKIE_SECURE=true
#   CORS_ORIGINS=https://tu-dominio.com
#   DATABASE_URL=postgresql://...

# 2. Iniciar stack
docker-compose -f docker-compose.prod.yml up -d

# 3. Verificar salud
curl https://tu-dominio.com/api/health
```

### Servicios Docker
| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| Nginx | 80/443 | Reverse proxy, SSL, rate limiting |
| Backend | 8000 | FastAPI (solo accesible vía nginx) |
| Frontend | — | Servido estático por nginx |
| PostgreSQL | 5432 | Base de datos |
| Redis | 6379 | Cache y blacklist |

### WireGuard VPN (Opcional)
Para ocultar tu IP real en requests a APIs externas:
```bash
sudo bash setup-vpn.sh
sudo wg-quick up wg0
curl https://ipinfo.io  # Verificar IP
```

---

## 🔒 Seguridad

### Modelo de Autenticación
```
Usuario ──► Registro/Login ──► JWT (access + refresh)
                              │
                              ▼
                    ┌─────────────────┐
                    │  httpOnly Cookie │
                    │  SameSite=Strict │
                    │  Secure (prod)   │
                    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  UserSession DB  │
                    │  IP + UA + Exp   │
                    └─────────────────┘
```

### Tiers de Acceso
| Tier | Descripción |
|------|-------------|
| `restricted` | Lectura básica de datos OSINT |
| `full` | + Mesh governance, honeypots, cyber intel |
| `admin` | + Dashboard administrativo, gestión de usuarios |

### Headers de Seguridad HTTP
```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'; ...
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

---

## 🧪 Testing

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# Con cobertura
python -m pytest tests/ -v --cov=. --cov-report=html

# Tests específicos
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_api.py -v
```

### Cobertura Actual
| Módulo | Tests | Estado |
|--------|-------|--------|
| Auth | 14 | ✅ Login, registro, cookies, roles, rate limit |
| API | 16 | ✅ Endpoints protegidos, validación, permisos |
| Wormhole | — | 🔄 Pendiente |
| Mesh | — | 🔄 Pendiente |
| Honeypot | — | 🔄 Pendiente |

---

## 📖 API Documentation

FastAPI genera documentación automática:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

### Endpoints Principales
```
POST   /api/auth/register          Registro de usuario
POST   /api/auth/login             Login (setea cookies)
POST   /api/auth/logout            Logout (revoca sesión)
GET    /api/auth/me                Info del usuario actual
GET    /api/auth/sessions          Sesiones activas
DELETE /api/auth/sessions/{id}     Revocar sesión

GET    /api/layers/{layer}         Datos de capa geoespacial
GET    /api/aviation/flights       Vuelos en tiempo real
GET    /api/ais/ships              Barcos AIS
GET    /api/cyber/threats          Amenazas de malware

POST   /api/wormhole/tunnel/create Crear túnel encriptado
GET    /api/wormhole/tunnels       Listar túneles propios

GET    /api/mesh/proposals         Propuestas de gobernanza
POST   /api/mesh/proposal          Crear propuesta (full/admin)

GET    /api/honeypot/status        Estado de honeypots
POST   /api/honeypot/inject        Inyectar honeypot (full/admin)

GET    /api/admin/dashboard        Dashboard admin (admin only)
GET    /api/admin/users            Lista de usuarios (admin only)
```

---

## 🔧 Troubleshooting

### Error: "Rate limit exceeded"
```bash
# Verificar headers de rate limit
curl -I http://localhost:8000/api/health
# X-RateLimit-Remaining: XX
```

### Error: "Invalid or expired token"
```bash
# El token expiró (24h) o fue revocado
# Refrescar: POST /api/auth/refresh
# O hacer login de nuevo
```

### Error: "403 Forbidden"
```bash
# Tu tier no tiene permiso para este endpoint
# restricted → full → admin
```

### Docker: "Connection refused"
```bash
# Verificar que todos los servicios están healthy
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs backend
```

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crea una rama (`git checkout -b feature/nueva-funcionalidad`)
3. Commitea tus cambios (`git commit -am 'Agrega nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Abre un Pull Request

### Guías
- Seguir PEP 8 para Python
- Usar TypeScript strict para frontend
- Agregar tests para nuevos endpoints
- Documentar cambios en `CHANGELOG.md`

---

## 📝 Licencia

MIT License - Ver [LICENSE](LICENSE) para detalles.

> **Disclaimer:** Esta plataforma es para investigación académica y seguridad. Todos los datos consultados son públicos. El volumen y automatización pueden levantar banderas en algunas jurisdicciones.

---

<p align="center">
  <strong>🦈 TU-OSINT-PLATFORM</strong><br>
  Inteligencia de fuentes abiertas, hecha con código.
</p>
