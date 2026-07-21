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
    launchctl bootout "gui/$(id -u)/com.agentium.voice" 2>/dev/null || warn "bootout failed"
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

# Remove UI companion (macOS launchd + files)
if [[ "${SVC_MGR:-}" == "launchd" ]]; then
    launchctl bootout "gui/$(id -u)/com.agentium.voice-ui" 2>/dev/null || warn "UI bootout failed"
    rm -f "$HOME/Library/LaunchAgents/com.agentium.voice-ui.plist"
    log "UI launchd plist removed"
fi
rm -rf "$HOME/.agentium/voice-ui"
log "UI companion files removed"

# Clean UI entries from rc files (Linux nohup path)
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    [[ -f "$rc" ]] || continue
    sed -i '/voice-ui\/run_voice_ui/d' "$rc" 2>/dev/null || true
done

log "Venv and conf files left in $HOME/.agentium (remove manually if desired)"
rm -f "$HOME/.agentium/voice-installed.marker"
log "install marker removed"
log "=== Uninstall complete ==="