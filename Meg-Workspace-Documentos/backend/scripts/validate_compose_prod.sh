#!/bin/bash
# validate_compose_prod.sh
#
# PENDIENTE I del plan de continuación: docker-compose.prod.yml usa
# `ports: !override []` en db/redis/minio para que esos servicios NO
# expongan puertos al host en producción. Eso depende de que la
# versión de Docker Compose soporte los tags de merge del Compose Spec
# (!override / !reset), agregados en Compose 2.24.4 (confirmado contra
# el changelog upstream de docker/compose). Antes, esto se dejaba como
# nota "SIN VERIFICAR" en un comentario del propio compose file -- una
# nota no falla el build si la versión del entorno no soporta el tag.
# Este script sí falla (exit 1), y se corre en CI (ver
# .github/workflows/ci.yml, job compose-validate) en cada push, además
# de poder correrse a mano antes de un deploy real.
#
# SIN VERIFICAR EN ESTE SANDBOX: Docker no está disponible aquí (sin
# red, sin daemon). La lógica del script se revisó con `bash -n`
# (sintaxis) y `shellcheck` si está disponible, pero la primera vez que
# esto se ejecuta de verdad contra Docker real es en CI.
set -euo pipefail

COMPOSE_MIN_VERSION="2.24.4"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
BASE_FILE="$BACKEND_DIR/docker-compose.yml"
PROD_FILE="$BACKEND_DIR/docker-compose.prod.yml"

fail() {
    echo "❌ $1" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker no está instalado en este entorno."
docker compose version >/dev/null 2>&1 || fail "el plugin 'docker compose' (v2) no está disponible."

[ -f "$BASE_FILE" ] || fail "no se encontró $BASE_FILE"
[ -f "$PROD_FILE" ] || fail "no se encontró $PROD_FILE"

# ─── 1. Versión de Compose ────────────────────────────────────────
# `docker compose version --short` imprime algo como "2.29.7".
raw_version="$(docker compose version --short 2>/dev/null || true)"
if [ -z "$raw_version" ]; then
    fail "no se pudo determinar la versión de 'docker compose'."
fi

version_ge() {
    # Compara dos versiones "x.y.z" -- true (0) si $1 >= $2.
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" = "$1" ]
}

if ! version_ge "$raw_version" "$COMPOSE_MIN_VERSION"; then
    fail "Docker Compose $raw_version detectado -- se requiere >= $COMPOSE_MIN_VERSION para que 'ports: !override []' funcione (soporte de tags !override/!reset, Compose Spec ene-2024). Con una versión más vieja, el merge por default CONCATENA las listas de puertos en vez de reemplazarlas, y db/redis/minio quedarían expuestos al host de todas formas."
fi
echo "✅ Docker Compose $raw_version >= $COMPOSE_MIN_VERSION"

# ─── 2. Variables requeridas por el compose de prod ───────────────
# docker-compose.prod.yml usa ${VAR:?mensaje} -- si faltan, 'config'
# truena. Para validar el merge no hace falta que sean secretos reales.
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ci-validation-only}"
export SECRET_KEY="${SECRET_KEY:-$(printf 'a%.0s' {1..64})}"
export MINIO_ROOT_USER="${MINIO_ROOT_USER:-ci-validation-only}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-ci-validation-only}"

# ─── 3. Resolver el merge y revisar puertos ───────────────────────
merged_json="$(docker compose -f "$BASE_FILE" -f "$PROD_FILE" config --format json)" \
    || fail "'docker compose config' falló al fusionar $BASE_FILE + $PROD_FILE."

python3 - "$merged_json" << 'PYEOF'
import json
import sys

merged = json.loads(sys.argv[1])
services = merged.get("services", {})

deben_estar_cerrados = ["db", "redis", "minio"]
fallas = []

for nombre in deben_estar_cerrados:
    servicio = services.get(nombre)
    if servicio is None:
        fallas.append(f"servicio '{nombre}' no existe en el compose fusionado")
        continue
    puertos = servicio.get("ports")
    if puertos:
        fallas.append(f"servicio '{nombre}' SIGUE exponiendo puertos al host: {puertos}")

if fallas:
    print("❌ El merge de docker-compose.prod.yml no cerró los puertos esperados:")
    for f in fallas:
        print(f"   - {f}")
    sys.exit(1)

print(f"✅ Puertos cerrados correctamente en: {', '.join(deben_estar_cerrados)}")
PYEOF

echo "✅ docker-compose.prod.yml validado: versión de Compose soportada y puertos internos cerrados."
