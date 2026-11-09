#!/bin/bash
# generate-client.sh - Genera cliente TypeScript desde OpenAPI

set -e

API_URL="${API_URL:-http://localhost:8000}"
OUTPUT_DIR="${OUTPUT_DIR:-./megalodon-client-ts}"

echo "Generando cliente TypeScript desde OpenAPI..."
echo "API URL: $API_URL"
echo "Output: $OUTPUT_DIR"

if ! command -v openapi-generator-cli &> /dev/null; then
    echo "Instalando openapi-generator-cli..."
    npm install -g @openapitools/openapi-generator-cli
fi

curl -s "$API_URL/openapi.json" -o /tmp/megalodon-openapi.json

openapi-generator-cli generate \
    -i /tmp/megalodon-openapi.json \
    -g typescript-fetch \
    -o "$OUTPUT_DIR" \
    --additional-properties=
        npmName=megalodon-client,
        npmVersion=4.0.0,
        supportsES6=true,
        modelPropertyNaming=original,
        withInterfaces=true

echo "Cliente generado en $OUTPUT_DIR"
