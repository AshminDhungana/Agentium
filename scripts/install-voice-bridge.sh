#!/usr/bin/env bash
# =============================================================================
# scripts/install-voice-bridge.sh — Agentium voice bridge installer (Phase 2+3)
# Reads ~/.agentium/env.conf written by detect-host.sh
# Creates a venv, installs Python deps, registers the OS service.
# Every step is wrapped in run_or_warn() so one failure never stops the rest.
# =============================================================================
set -euo pipefail

CONF_DIR="$HOME/.agentium"
CONF_FILE="$CONF_DIR/env.conf"
LOG_FILE="$CONF_DIR/install.log"
VENV_DIR="$CONF_DIR/voice-venv"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_DIR="$REPO_ROOT/voice-bridge"

mkdir -p "$CONF_DIR"
: > "$LOG_FILE"

# ── helpers ───────────────────────────────────────────────────────────────────
log()        { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn()       { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; }
run_or_warn() {
  local label="$1"; shift
  if "$@" >> "$LOG_FILE" 2>&1; then
    log "  ✓ $label"
  else
    warn "$label failed (exit $?) — continuing"
  fi
}

# ── Load env.conf ─────────────────────────────────────────────────────────────
if [[ ! -f "$CONF_FILE" ]]; then
  warn "env.conf not found — run detect-host.sh first"
  exit 1
fi
# shellcheck disable=SC1090
source "$CONF_FILE"

log "=== Agentium Voice Bridge Installer ==="
log "OS_FAMILY=$OS_FAMILY  PKG_MGR=$PKG_MGR  PYTHON_BIN=$PYTHON_BIN"

# ── Step 2.1  System audio packages ───────────────────────────────────────────
log "Step 2.1 — Installing system audio packages"
case "$PKG_MGR" in
  apt)
    run_or_warn "apt update"         sudo apt-get update -qq
    run_or_warn "portaudio19-dev"    sudo apt-get install -y -qq portaudio19-dev
    run_or_warn "python3-pyaudio"    sudo apt-get install -y -qq python3-pyaudio
    run_or_warn "espeak"             sudo apt-get install -y -qq espeak espeak-data
    run_or_warn "alsa-utils"         sudo apt-get install -y -qq alsa-utils
    ;;
  brew)
    run_or_warn "portaudio"          brew install portaudio
    run_or_warn "espeak"             brew install espeak
    ;;
  dnf)
    run_or_warn "portaudio-devel"    sudo dnf install -y portaudio-devel
    run_or_warn "espeak"             sudo dnf install -y espeak
    ;;
  pacman)
    run_or_warn "portaudio"          sudo pacman -S --noconfirm portaudio
    run_or_warn "espeak-ng"          sudo pacman -S --noconfirm espeak-ng
    ;;
  *)
    warn "Unknown pkg manager '$PKG_MGR' — skipping system packages"
    ;;
esac

# ── Step 2.2  Python venv ─────────────────────────────────────────────────────
log "Step 2.2 — Creating Python venv at $VENV_DIR"
if [[ "$PYTHON_BIN" == "python3_missing" ]]; then
  warn "Python ≥ 3.10 not found — skipping venv and pip installs"
else
  run_or_warn "create venv"  "$PYTHON_BIN" -m venv "$VENV_DIR"

  # Step 2.3 — pip install
  log "Step 2.3 — Installing Python packages"
  VENV_PIP="$VENV_DIR/bin/pip"
  run_or_warn "pip upgrade"           "$VENV_PIP" install --upgrade pip
  run_or_warn "install websockets"    "$VENV_PIP" install "websockets>=12.0"
  run_or_warn "install SpeechRecog"   "$VENV_PIP" install "SpeechRecognition>=3.10.4"
  run_or_warn "install PyAudio"       "$VENV_PIP" install "PyAudio>=0.2.14"
  run_or_warn "install pyttsx3"       "$VENV_PIP" install "pyttsx3>=2.90"
  run_or_warn "install python-jose"   "$VENV_PIP" install "python-jose[cryptography]>=3.3.0"

  # Write the venv path to env.conf so main.py can find it
  echo "VENV_PYTHON=$VENV_DIR/bin/python" >> "$CONF_FILE"
fi

# ── Step 3  Service registration ──────────────────────────────────────────────
log "Step 3 — Registering OS service (SVC_MGR=$SVC_MGR)"

BRIDGE_CMD="${VENV_DIR}/bin/python ${BRIDGE_DIR}/main.py"

case "$SVC_MGR" in

  systemd)
    SERVICE_FILE="$HOME/.config/systemd/user/agentium-voice.service"
    mkdir -p "$(dirname "$SERVICE_FILE")"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Agentium Voice Bridge
After=network.target

[Service]
Type=simple
ExecStart=$BRIDGE_CMD
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
EnvironmentFile=$CONF_FILE

[Install]
WantedBy=default.target
EOF
    run_or_warn "systemctl daemon-reload"   systemctl --user daemon-reload
    run_or_warn "systemctl enable"          systemctl --user enable agentium-voice
    run_or_warn "systemctl start"           systemctl --user start  agentium-voice
    log "  Service: systemctl --user status agentium-voice"
    ;;

  launchd)
    PLIST="$HOME/Library/LaunchAgents/com.agentium.voice.plist"
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.agentium.voice</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>${BRIDGE_DIR}/main.py</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardOutPath</key>   <string>${CONF_DIR}/voice-bridge.log</string>
  <key>StandardErrorPath</key> <string>${CONF_DIR}/voice-bridge.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>BACKEND_URL</key> <string>${BACKEND_URL}</string>
    <key>WS_PORT</key>     <string>9999</string>
    <key>WAKE_WORD</key>   <string>agentium</string>
  </dict>
</dict>
</plist>
EOF
    run_or_warn "launchctl load" launchctl load -w "$PLIST"
    log "  Service: launchctl list com.agentium.voice"
    ;;

  wsl2)
    STARTUP="$CONF_DIR/start-voice-bridge.sh"
    cat > "$STARTUP" <<EOF
#!/usr/bin/env bash
# Auto-generated by install-voice-bridge.sh
source "$CONF_FILE"
exec $BRIDGE_CMD >> "$CONF_DIR/voice-bridge.log" 2>&1 &
echo \$! > "$CONF_DIR/voice-bridge.pid"
EOF
    chmod +x "$STARTUP"
    log "  WSL2: run '$STARTUP' manually or add to your .bashrc/.profile"
    warn "WSL2 has no native service manager — manual start required"
    ;;

  *)
    warn "No service manager detected — start the bridge manually:"
    warn "  $BRIDGE_CMD"
    ;;
esac

log "=== Installation complete. Check $LOG_FILE for any warnings. ==="