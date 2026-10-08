# scripts/regen-sdk-types.ps1
# Regenerate sdk/typescript/src/generated-types.ts from the current backend
# code. No running services required. Usage (from repo root):
#   powershell -File scripts/regen-sdk-types.ps1   (or: make regen-sdk-types)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

try {
  python scripts/export_openapi.py
} catch {
  Write-Host ""
  Write-Host "ERROR: static OpenAPI export failed."
  Write-Host "If a backend dependency is missing, run: pip install -r backend/requirements.txt"
  Write-Host "If an import-time env var is required, start the test stack:"
  Write-Host "  docker compose -f docker-compose.test.yml up -d"
  Write-Host "then re-run this command."
  exit 1
}

Push-Location sdk/typescript
npm run generate-types
Pop-Location

Remove-Item -ErrorAction SilentlyContinue sdk/typescript/openapi.json
Write-Host "Done - sdk/typescript/src/generated-types.ts regenerated. Review and commit the diff."
