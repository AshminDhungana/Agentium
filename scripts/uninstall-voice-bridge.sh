#!/usr/bin/env bash
# scripts/uninstall-voice-bridge.sh
# Stops and removes the voice bridge service. Non-destructive to Docker stack.

set -euo pipefail

CONF_FILE="$HOME/.agentium/env.conf"

warn() { echo "[WARN] $*" >&2; }
log()  { echo "[$(date '+%H:%M:%S')] $*"; }

if [[ ! -f "$CONF_FILE" ]]; then
  warn "env.conf not found — nothing to uninstall"
  exit 0
fi

# shellcheck disable=SC1090
source "$CONF_FILE"

log "=== Agentium Voice Bridge Uninstaller ==="

case "${SVC_MGR:-none}" in
  systemd)
    systemctl --user stop    agentium-voice 2>/dev/null || warn "stop failed"
    systemctl --user disable agentium-voice 2>/dev/null || warn "disable failed"
    rm -f "$HOME/.config/systemd/user/agentium-voice.service"
    systemctl --user daemon-reload || true
    log "systemd service removed"
    ;;
  launchd)
    launchctl unload -w "$HOME/Library/LaunchAgents/com.agentium.voice.plist" 2>/dev/null || warn "unload failed"
    rm -f "$HOME/Library/LaunchAgents/com.agentium.voice.plist"
    log "launchd plist removed"
    ;;
  wsl2)
    PID_FILE="$HOME/.agentium/voice-bridge.pid"
    if [[ -f "$PID_FILE" ]]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || warn "process already stopped"
      rm -f "$PID_FILE"
    fi
    log "WSL2 bridge process stopped"
    ;;
  *)
    warn "No known service manager — kill manually: pkill -f 'voice-bridge/main.py'"
    ;;
esac

log "Venv and conf files left in $HOME/.agentium (remove manually if desired)"
log "=== Uninstall complete ==="