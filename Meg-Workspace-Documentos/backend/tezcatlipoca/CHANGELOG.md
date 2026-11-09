# Changelog

All notable changes to this project will be documented in this file.

## [2.3.5] - 2026-07-16

### Security
- Added httpOnly cookies with SameSite=Strict for JWT storage
- Implemented role-based access control (restricted/full/admin)
- Added global rate limiting middleware (100 req/min)
- Added audit logging for all API requests
- Fixed path traversal vulnerability in file uploads
- Enforced HTTPS on all external API calls
- Added SSL verification to all HTTP clients
- Implemented token revocation (blacklist in Redis + DB)
- Added session tracking in database (IP, User-Agent)

### Infrastructure
- Hardened Dockerfile (multi-stage, non-root, healthcheck)
- Added security headers to Nginx (CSP, HSTS, X-Frame)
- Pinned Docker image versions for reproducibility
- Added resource limits to docker-compose.prod.yml
- Added WireGuard VPN setup script

### API Protection
- Added authentication to wormhole, mesh, honeypot routers
- Added Pydantic validation to all sensitive endpoints
- Implemented owner checks on private resources
- Added require_role dependency for tier-based access

### External API Hardening
- Added rotating User-Agent with project identification
- Implemented jitter (1-3s) between requests
- Added exponential backoff on rate limiting
- Increased cache TTLs (2h-6h depending on source)
- Created secure_requests module for all external calls

### Testing
- Added 14 auth tests (registration, login, cookies, roles)
- Added 16 API tests (protected endpoints, validation)
- Added conftest.py with TestClient and DB fixtures

### Frontend
- Removed localStorage for token storage
- Implemented credentials: 'include' for cookie transmission
- Fixed XSS vulnerability in Solar Geo (innerHTML → textContent)

## [2.3.0] - Previous
- Initial secure release
- Basic JWT authentication
- OSINT data aggregation
- Mesh governance framework
