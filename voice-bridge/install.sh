#!/usr/bin/env bash
# voice-bridge/install.sh
# Entry-point: runs OS detection then the full dependency installer.
# Usage:  bash voice-bridge/install.sh
# Or via Makefile:  make install-voice

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Agentium Voice Bridge Installer ==="
echo "Repo root : $REPO_ROOT"
echo ""

# ── Phase 1: OS detection ──────────────────────────────────────────────────────
echo "[install.sh] Running OS detection…"
if ! bash "$REPO_ROOT/scripts/detect-host.sh"; then
    echo "[WARN] detect-host.sh exited non-zero — continuing anyway"
fi

# ── Phase 2+3: deps + service registration ─────────────────────────────────────
echo "[install.sh] Running dependency installer…"
if ! bash "$REPO_ROOT/scripts/install-voice-bridge.sh"; then
    echo "[WARN] install-voice-bridge.sh exited non-zero — check ~/.agentium/install.log"
fi

echo ""
echo "=== Voice bridge installation complete ==="
echo "Check ~/.agentium/install.log for details."
echo "Run 'make voice-status' to confirm the service is active."