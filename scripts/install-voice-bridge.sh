#!/usr/bin/env bash
# =============================================================================
# scripts/install-voice-bridge.sh -- Agentium voice bridge installer (Phase 2+3)
# Reads ~/.agentium/env.conf written by detect-host.sh
# Creates a venv, installs Python deps, registers + STARTS the OS service.
# Every step is wrapped in run_or_warn() so one failure never stops the rest.
#
# Supported service managers (all auto-start the bridge immediately):
#   systemd  -- Linux with systemd user session
#   launchd  -- macOS
#   wsl2     -- WSL2 (starts via nohup, adds to .bashrc for persistence)
#   none     -- Linux without systemd (starts via nohup, adds rc file entry)
# =============================================================================
set -euo pipefail

# Only use sudo when we are not already root and sudo exists.
if [[ $EUID -eq 0 ]] || ! command -v sudo &>/dev/null; then SUDO=""; else SUDO="sudo"; fi

CONF_DIR="$HOME/.agentium"
CONF_FILE="$CONF_DIR/env.conf"
LOG_FILE="$CONF_DIR/install.log"
VENV_DIR="$CONF_DIR/voice-venv"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_DIR="$REPO_ROOT/voice-bridge"

mkdir -p "$CONF_DIR"
: > "$LOG_FILE"

# -- helpers ------------------------------------------------------------------
log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN] $*" | tee -a "$LOG_FILE" >&2; }

run_or_warn() {
    local label="$1"; shift
    if "$@" >> "$LOG_FILE" 2>&1; then
        log "  OK: $label"
    else
        warn "$label failed (exit $?) -- continuing"
    fi
}

# -- Load env.conf ------------------------------------------------------------
if [[ ! -f "$CONF_FILE" ]]; then
    warn "env.conf not found -- run detect-host.sh first"
    exit 1
fi
# shellcheck disable=SC1090
source "$CONF_FILE"

log "=== Agentium Voice Bridge Installer ==="
log "OS_FAMILY=$OS_FAMILY  PKG_MGR=$PKG_MGR  PYTHON_BIN=$PYTHON_BIN  SVC_MGR=$SVC_MGR"

# =============================================================================
# Step 2.1 -- System audio packages
# =============================================================================
log "Step 2.1 -- Installing system audio packages"
case "$PKG_MGR" in
    apt)
        run_or_warn "apt update"        $SUDO apt-get update -qq
        run_or_warn "portaudio19-dev"   $SUDO apt-get install -y -qq portaudio19-dev
        run_or_warn "python3-pyaudio"   $SUDO apt-get install -y -qq python3-pyaudio
        run_or_warn "espeak"            $SUDO apt-get install -y -qq espeak espeak-data
        run_or_warn "alsa-utils"        $SUDO apt-get install -y -qq alsa-utils
        ;;
    brew)
        # brew must NOT run as root -- run as the actual user when we are root.
        BREW_USER="${SUDO_USER:-$USER}"
        if [[ -n "$SUDO" ]]; then
            run_or_warn "portaudio" $SUDO -u "$BREW_USER" brew install portaudio
            run_or_warn "espeak-ng" $SUDO -u "$BREW_USER" brew install espeak-ng
        else
            run_or_warn "portaudio" brew install portaudio
            run_or_warn "espeak-ng" brew install espeak-ng
        fi
        ;;
    dnf)
        run_or_warn "portaudio-devel"   $SUDO dnf install -y portaudio-devel
        run_or_warn "espeak"            $SUDO dnf install -y espeak
        ;;
    pacman)
        run_or_warn "portaudio"         $SUDO pacman -S --noconfirm portaudio
        run_or_warn "espeak-ng"         $SUDO pacman -S --noconfirm espeak-ng
        ;;
    zypper)
        run_or_warn "portaudio-devel"   $SUDO zypper install -y portaudio-devel
        run_or_warn "espeak-ng"         $SUDO zypper install -y espeak-ng
        ;;
    apk)
        run_or_warn "alsa-lib-dev"  $SUDO apk add --no-cache alsa-lib-dev
        run_or_warn "portaudio-dev" $SUDO apk add --no-cache portaudio-dev
        run_or_warn "espeak"        $SUDO apk add --no-cache espeak
        ;;
    *)
        warn "Unknown pkg manager '$PKG_MGR' -- skipping system audio packages"
        ;;
esac

# =============================================================================
# Step 2.2 -- Python venv
# =============================================================================
log "Step 2.2 -- Creating Python venv at $VENV_DIR"

if [[ "$PYTHON_BIN" == "python3_missing" ]]; then
    warn "Python 3.10+ not found -- skipping venv and pip installs"
else
    run_or_warn "create venv"   "$PYTHON_BIN" -m venv "$VENV_DIR"

    log "Step 2.3 -- Installing Python packages"
    VENV_PIP="$VENV_DIR/bin/pip"
    run_or_warn "pip upgrade"           "$VENV_PIP" install --upgrade pip
    run_or_warn "install websockets"    "$VENV_PIP" install "websockets>=12.0"
    run_or_warn "install SpeechRecog"   "$VENV_PIP" install "SpeechRecognition>=3.10.4"
    run_or_warn "install PyAudio"       "$VENV_PIP" install "PyAudio>=0.2.14"
    run_or_warn "install pyttsx3"       "$VENV_PIP" install "pyttsx3>=2.90"
    run_or_warn "install python-jose"   "$VENV_PIP" install "python-jose[cryptography]>=3.3.0"
    # sounddevice: neural TTS playback + microphone fallback when PyAudio
    # lacks a wheel for the host Python version (e.g. 3.12+).
    run_or_warn "install sounddevice"   "$VENV_PIP" install "sounddevice>=0.4.6"
    run_or_warn "install aiohttp"       "$VENV_PIP" install "aiohttp>=3.9"

    # Write venv path so main.py can find it
    grep -q "^VENV_PYTHON=" "$CONF_FILE" 2>/dev/null || \
        echo "VENV_PYTHON=$VENV_DIR/bin/python" >> "$CONF_FILE"
fi

# =============================================================================
# Step 3 -- Service registration + immediate start
# =============================================================================
log "Step 3 -- Registering OS service (SVC_MGR=$SVC_MGR)"

BRIDGE_PY="$VENV_DIR/bin/python"
BRIDGE_SCRIPT="$BRIDGE_DIR/main.py"
BRIDGE_CMD="$BRIDGE_PY $BRIDGE_SCRIPT"
BRIDGE_LOG="$CONF_DIR/voice-bridge.log"
PID_FILE="$CONF_DIR/voice-bridge.pid"

# Helper: start the bridge right now via nohup (used by wsl2 + none paths)
start_bridge_now() {
    # Kill any existing instance first
    if [[ -f "$PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
        if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
            kill "$old_pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$PID_FILE"
    fi

    nohup $BRIDGE_CMD >> "$BRIDGE_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1

    if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        log "  Bridge started (PID $(cat "$PID_FILE")). Log: $BRIDGE_LOG"
    else
        warn "Bridge process exited immediately -- check $BRIDGE_LOG"
    fi
}

# Helper: add a line to a shell rc file only once
add_to_rc() {
    local rc_file="$1"
    local line="$2"
    touch "$rc_file"
    if ! grep -qF "$line" "$rc_file" 2>/dev/null; then
        echo "" >> "$rc_file"
        echo "# Agentium Voice Bridge -- auto-added by installer" >> "$rc_file"
        echo "$line" >> "$rc_file"
        log "  Added to $rc_file: $line"
    else
        log "  Already in $rc_file: $line"
    fi
}

case "$SVC_MGR" in

    # -------------------------------------------------------------------------
    # systemd (Linux desktop / server)
    # -------------------------------------------------------------------------
    systemd)
        SERVICE_FILE="$HOME/.config/systemd/user/agentium-voice.service"
        mkdir -p "$(dirname "$SERVICE_FILE")"

        cat > "$SERVICE_FILE" << EOF
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

        # Ensure the user systemd session is reachable.
        # On some distros DBUS_SESSION_BUS_ADDRESS is not exported to sub-shells.
        if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
            # Try to find it from the running user session
            local_uid=$(id -u)
            dbus_addr=$(grep -r "DBUS_SESSION_BUS_ADDRESS" \
                /proc/*/environ 2>/dev/null \
                | grep "uid=$local_uid" 2>/dev/null \
                | head -1 \
                | tr '\0' '\n' \
                | grep DBUS_SESSION \
                | cut -d= -f2- || true)
            if [[ -n "$dbus_addr" ]]; then
                export DBUS_SESSION_BUS_ADDRESS="$dbus_addr"
                log "  Recovered DBUS_SESSION_BUS_ADDRESS"
            fi
        fi

        if systemctl --user daemon-reload >> "$LOG_FILE" 2>&1; then
            run_or_warn "systemctl enable"  systemctl --user enable agentium-voice
            run_or_warn "systemctl start"   systemctl --user start  agentium-voice
            log "  systemd service running. Check: systemctl --user status agentium-voice"
        else
            warn "systemctl --user not reachable (no D-Bus session) -- falling back to nohup start"
            # Still enable so it auto-starts on next login
            systemctl --user enable agentium-voice >> "$LOG_FILE" 2>&1 || true
            start_bridge_now
        fi
        ;;

    # -------------------------------------------------------------------------
    # launchd (macOS)
    # -------------------------------------------------------------------------
    launchd)
        PLIST="$HOME/Library/LaunchAgents/com.agentium.voice.plist"
        mkdir -p "$(dirname "$PLIST")"

        cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.agentium.voice</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>${BRIDGE_SCRIPT}</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <true/>
  <key>StandardOutPath</key>   <string>${BRIDGE_LOG}</string>
  <key>StandardErrorPath</key> <string>${BRIDGE_LOG}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>BACKEND_URL</key> <string>${BACKEND_URL}</string>
    <key>WS_PORT</key>     <string>${WS_PORT:-9999}</string>
    <key>WAKE_WORD</key>   <string>${WAKE_WORD:-agentium}</string>
  </dict>
</dict>
</plist>
EOF

        # launchd requires the plist to be owned by the user and not group/world writable.
        chmod 644 "$PLIST"
        chown "$USER" "$PLIST" 2>/dev/null || true

        # Use the modern (non-deprecated) bootstrap/kickstart API.
        launchctl bootout "gui/$(id -u)/com.agentium.voice" >> "$LOG_FILE" 2>&1 || true
        if launchctl bootstrap "gui/$(id -u)" "$PLIST" >> "$LOG_FILE" 2>&1 && \
           launchctl kickstart "gui/$(id -u)/com.agentium.voice" >> "$LOG_FILE" 2>&1; then
            log "  launchd service bootstrapped and started."
            log "  Check: launchctl print gui/$(id -u)/com.agentium.voice"
        else
            warn "launchctl bootstrap failed -- falling back to nohup start"
            start_bridge_now
        fi
        ;;

    # -------------------------------------------------------------------------
    # WSL2 -- no native service manager accessible from inside WSL
    # Strategy: start via nohup right now + add to .bashrc for persistence
    # -------------------------------------------------------------------------
    wsl2)
        log "  WSL2 detected -- starting bridge via nohup and persisting in .bashrc"

        # Write a dedicated start script
        STARTUP_SCRIPT="$CONF_DIR/start-voice-bridge.sh"
        cat > "$STARTUP_SCRIPT" << EOF
#!/usr/bin/env bash
# Auto-generated by Agentium installer
# Starts the voice bridge if it is not already running.
PID_FILE="$PID_FILE"
BRIDGE_LOG="$BRIDGE_LOG"
if [[ -f "\$PID_FILE" ]] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    exit 0   # already running
fi
source "$CONF_FILE"
nohup $BRIDGE_CMD >> "\$BRIDGE_LOG" 2>&1 &
echo \$! > "\$PID_FILE"
EOF
        chmod +x "$STARTUP_SCRIPT"

        # Start it right now
        start_bridge_now

        # Persist across shell sessions -- add to every common rc file found
        for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
            if [[ -f "$rc" ]] || [[ "$rc" == "$HOME/.bashrc" ]]; then
                add_to_rc "$rc" "bash '$STARTUP_SCRIPT' &"
            fi
        done

        log "  Bridge started. It will restart automatically on each new WSL2 shell."
        ;;

    # -------------------------------------------------------------------------
    # none -- Linux without systemd (e.g. Alpine, Docker-in-Docker, old distros)
    # Strategy: nohup start now + add to /etc/rc.local or ~/.profile
    # -------------------------------------------------------------------------
    none)
        log "  No systemd -- starting bridge via nohup and adding to startup"

        STARTUP_SCRIPT="$CONF_DIR/start-voice-bridge.sh"
        cat > "$STARTUP_SCRIPT" << EOF
#!/usr/bin/env bash
# Auto-generated by Agentium installer
PID_FILE="$PID_FILE"
BRIDGE_LOG="$BRIDGE_LOG"
if [[ -f "\$PID_FILE" ]] && kill -0 "\$(cat "\$PID_FILE")" 2>/dev/null; then
    exit 0
fi
source "$CONF_FILE"
nohup $BRIDGE_CMD >> "\$BRIDGE_LOG" 2>&1 &
echo \$! > "\$PID_FILE"
EOF
        chmod +x "$STARTUP_SCRIPT"

        # Start immediately
        start_bridge_now

        # Persist: try /etc/rc.local first (system-wide), fall back to ~/.profile
        if [[ -f /etc/rc.local ]] && [[ -w /etc/rc.local ]]; then
            add_to_rc /etc/rc.local "bash '$STARTUP_SCRIPT'"
        elif sudo test -f /etc/rc.local 2>/dev/null; then
            # Add via sudo
            if ! sudo grep -qF "$STARTUP_SCRIPT" /etc/rc.local 2>/dev/null; then
                echo "bash '$STARTUP_SCRIPT'" | sudo tee -a /etc/rc.local >> "$LOG_FILE" 2>&1
                log "  Added to /etc/rc.local (via sudo)"
            fi
        else
            add_to_rc "$HOME/.profile" "bash '$STARTUP_SCRIPT' &"
            add_to_rc "$HOME/.bashrc"  "bash '$STARTUP_SCRIPT' &"
        fi
        ;;

    *)
        warn "Unknown SVC_MGR='$SVC_MGR' -- starting bridge via nohup only (no persistence)"
        start_bridge_now
        ;;
esac

# =============================================================================
# Phase 4  Desktop UI companion (optional)
# =============================================================================
log "Phase 4 -- Installing Desktop UI companion"
install_voice_ui() {
    if [[ ! -f "$VENV_PIP" ]]; then
        warn "pip not found at $VENV_PIP -- cannot install UI dependencies"
        return 1
    fi
    if [[ ! -d "$BRIDGE_DIR" ]]; then
        warn "voice-bridge dir not found -- cannot copy UI files"
        return 1
    fi

    log "  Installing PySide6 (this may take a while)..."
    if [[ "$OS_FAMILY" == "linux" ]] && [[ "$PKG_MGR" == "apt" ]]; then
        run_or_warn "install libgl1"      $SUDO apt-get install -y -qq libgl1 libegl1 libxkbcommon0 2>/dev/null || true
    fi

    if ! run_or_warn "install PySide6" "$VENV_PIP" install "PySide6>=6.5"; then
        warn "PySide6 install failed -- UI not available. Bridge works fine without it."
        return 1
    fi

    UI_DEST="$CONF_DIR/voice-ui"
    mkdir -p "$UI_DEST"
    if cp -r "$BRIDGE_DIR/ui/"* "$UI_DEST/" 2>/dev/null; then
        log "  UI files copied to $UI_DEST"
    else
        warn "Failed to copy UI files from $BRIDGE_DIR/ui"
        return 1
    fi
    if [[ -f "$BRIDGE_DIR/run_voice_ui.py" ]]; then
        cp "$BRIDGE_DIR/run_voice_ui.py" "$UI_DEST/"
    fi

    if [[ "$OS_FAMILY" == "macos" ]]; then
        UI_PLIST="$HOME/Library/LaunchAgents/com.agentium.voice-ui.plist"
        cat > "$UI_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>com.agentium.voice-ui</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>${UI_DEST}/run_voice_ui.py</string>
  </array>
  <key>RunAtLoad</key>         <true/>
  <key>KeepAlive</key>         <false/>
  <key>StandardOutPath</key>   <string>${CONF_DIR}/voice-ui.log</string>
  <key>StandardErrorPath</key> <string>${CONF_DIR}/voice-ui.log</string>
</dict>
</plist>
EOF
        chmod 644 "$UI_PLIST"
        chown "$USER" "$UI_PLIST" 2>/dev/null || true
        launchctl bootout "gui/$(id -u)/com.agentium.voice-ui" >> "$LOG_FILE" 2>&1 || true
        if launchctl bootstrap "gui/$(id -u)" "$UI_PLIST" >> "$LOG_FILE" 2>&1; then
            launchctl kickstart "gui/$(id -u)/com.agentium.voice-ui" >> "$LOG_FILE" 2>&1 || true
            log "  launchd UI agent bootstrapped."
        else
            warn "launchctl bootstrap for UI failed -- starting via nohup instead"
            nohup "$VENV_DIR/bin/python" "$UI_DEST/run_voice_ui.py" >> "$CONF_DIR/voice-ui.log" 2>&1 &
            log "  UI started via nohup (PID $!)"
        fi
    elif [[ "$OS_FAMILY" == "linux" ]]; then
        # Linux: best-effort start via nohup. Desktop environments without systemd
        # tray support will simply not show the UI; the bridge still works.
        nohup "$VENV_DIR/bin/python" "$UI_DEST/run_voice_ui.py" >> "$CONF_DIR/voice-ui.log" 2>&1 &
        log "  UI started via nohup (PID $!)"
        # Add to rc files for persistence on next login
        for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
            if [[ -f "$rc" ]] || [[ "$rc" == "$HOME/.bashrc" ]]; then
                add_to_rc "$rc" "nohup '$VENV_DIR/bin/python' '$UI_DEST/run_voice_ui.py' >> '$CONF_DIR/voice-ui.log' 2>&1 &"
            fi
        done
    fi
    log "  UI companion installed."
}
install_voice_ui || true

# --- Background: install Kokoro TTS (large deps, torch ~250MB) ---
# Runs via nohup so the installer can exit while the download continues.
log "  Launching background kokoro install (detached, may take several minutes)..."
nohup "$VENV_DIR/bin/pip" install kokoro soundfile --quiet >> "$LOG_FILE" 2>&1 &
log "  Kokoro install running detached (PID $!)"

# Signal successful install (consumed by voice-autoinstall guard + launchers)
touch "$CONF_DIR/voice-installed.marker"
log "Install marker written: $CONF_DIR/voice-installed.marker"

log "=== Installation complete. Check $LOG_FILE for any warnings. ==="