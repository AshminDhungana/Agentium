#!/usr/bin/env bash
# scripts/docker-scout.sh -- Run docker scout on all locally built images.
# Fails (exit 1) if HIGH or CRITICAL CVEs are found.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

THRESHOLD="${1:-high}"
EXIT_CODE=0

# Array of images to scan. These must be built before scanning.
IMAGES=(
    "agentium-backend:latest"
    "agentium-frontend:latest"
    "ghcr.io/ashmindhungana/agentium/whatsapp-bridge:main"
)

echo "Scanning images with Docker Scout..."
echo "   Threshold: ${THRESHOLD}+"
echo ""

for img in "${IMAGES[@]}"; do
    echo "---"
    echo "Image: ${img}"
    if ! docker scout cves --only-severity "${THRESHOLD}" "${img}" 2>/dev/null; then
        echo "  Warning: ${img}: HIGH/CRITICAL findings detected or scan failed."
        EXIT_CODE=1
    else
        echo "  OK: ${img}: No HIGH/CRITICAL findings."
    fi
    echo ""
done

echo "---"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "All images passed the CVE threshold (${THRESHOLD})."
else
    echo "Some images have HIGH/CRITICAL CVEs. See details above."
    echo "   Run 'docker scout recommendations <image>' for remediation."
fi

exit $EXIT_CODE
