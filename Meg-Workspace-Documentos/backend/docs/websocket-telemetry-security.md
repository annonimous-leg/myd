# WebSocket authentication and telemetry privacy acceptance

## WebSocket session boundary

- Accept browser WebSocket handshakes only when `Origin` exactly matches one entry in `CORS_ALLOWED_ORIGINS`.
- Authenticate using the HttpOnly session cookie only. Access tokens must never appear in query strings.
- Reuse the HTTP access-token validator, including expiration and revocation checks.
- Revalidate long-lived sockets before processing messages and after idle timeouts.
- Before subscribing to a progress task, verify its persisted owner against the authenticated tenant in the database. Unknown tasks and database failures fail closed.
- Do not accept a connection before Origin and session checks pass.

## Telemetry privacy boundary

- Exactly one FastAPI server span is emitted by the request-context middleware.
- W3C trace context is extracted as parent context; caller-supplied request IDs remain log/response correlation values, not span attributes.
- Server spans use bounded route templates and omit raw paths, query strings, host names, peer/client addresses, and exception messages/frames.
- HTTPX hooks redact URL and peer/address attributes before export.
- Sensitive request/response headers (authorization, cookies, tokens, secrets, API keys, passwords, sessions and credentials) are sanitized.
- Current regression tests exercise FastAPI server spans and HTTPX client span redaction. They do not certify attributes from SQLAlchemy, Redis or Celery instrumentation; those remain separate review items.

## Acceptance

Run unit and integration suites on the current recovery candidate, including:
- exact Origin allowlist, missing/untrusted Origin, and rejection before auth;
- no token query parameter accepted by either WebSocket endpoint;
- revoked/expired session rejection and tenant-owned task subscription;
- URL, query, host, IP and sensitive header redaction;
- W3C parent propagation, request context restoration, and exception-data suppression.

No merge or deployment is implied by a passing CI run. Production deployment still requires the actual domain allowlist and cookie configuration to be checked in the target environment.
