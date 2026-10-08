#!/usr/bin/env bash
# Regenerate sdk/typescript/src/generated-types.ts from the current backend
# code. No running services required. Usage (from repo root):
#   scripts/regen-sdk-types.sh   (or: make regen-sdk-types)
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python scripts/export_openapi.py; then
  echo ""
  echo "ERROR: static OpenAPI export failed."
  echo "If a backend dependency is missing, run: pip install -r backend/requirements.txt"
  echo "If an import-time env var is required, start the test stack:"
  echo "  docker compose -f docker-compose.test.yml up -d"
  echo "then re-run this command."
  exit 1
fi

cd sdk/typescript
npm run generate-types
cd ../..

rm -f sdk/typescript/openapi.json
echo "Done — sdk/typescript/src/generated-types.ts regenerated. Review and commit the diff."
