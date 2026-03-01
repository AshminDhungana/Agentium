# Agentium — Host-Native Voice Interface: Complete Implementation

> **Goal:** Detect the host OS at install time, set up a voice bridge process _outside_ Docker, and let the user speak to the Head of Council directly from their desktop after login — with full TTS playback and chat history sync. Every error is caught, logged with a warning, and the rest of the system continues running normally.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Structure](#2-file-structure)
3. [Phase 1 — OS Detection (`scripts/detect-host.sh`)](#3-phase-1--os-detection)
4. [Phase 2 — Dependency Installer (`scripts/install-voice-bridge.sh`)](#4-phase-2--dependency-installer)
5. [Phase 3 — Service Registration (systemd / launchd / WSL2)](#5-phase-3--service-registration)
6. [Phase 4 — Backend Voice Token API](#6-phase-4--backend-voice-token-api)
7. [Phase 5 — Voice Bridge Core (`voice-bridge/main.py`)](#7-phase-5--voice-bridge-core)
8. [Phase 6 — Frontend Integration](#8-phase-6--frontend-integration)
9. [Phase 7 — Docker Compose Wiring](#9-phase-7--docker-compose-wiring)
10. [Error Handling Reference](#10-error-handling-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  HOST OS                                                    │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  voice-bridge/main.py           │  microphone + speakers │
│  │  SecureVoiceBridge              │◄──────────────────────┤│
│  │  • Wake-word detection          │                        │
│  │  • STT  (Vosk offline / Google) │                        │
│  │  • TTS  (pyttsx3)               │                        │
│  │  • WS server  127.0.0.1:9999   │                        │
│  └──────────┬──────────────────────┘                        │
│             │  HTTP  (port 8000)  /  WS events              │
└─────────────┼───────────────────────────────────────────────┘
              │  Docker bridge network
┌─────────────▼───────────────────────────────────────────────┐
│  DOCKER                                                     │
│                                                             │
│  backend (FastAPI :8000)  ←→  Head of Council (LLM)        │
│  frontend (React   :3000)      redis / postgres / chroma    │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** every step that can fail is wrapped in its own error handler. A failed step prints a `[WARN]` or `[ERROR]` banner and either retries, falls back to a safe default, or skips that step — the rest of the installation and the rest of the bridge always continue.

---

## 2. File Structure

```
Agentium/
├── voice-bridge/
│   ├── main.py                  # SecureVoiceBridge — core bridge process
│   ├── requirements.txt         # Pinned Python deps
│   └── install.sh               # Entry-point: calls detect-host.sh then installer
│
├── scripts/
│   ├── detect-host.sh           # Phase 1 — OS probe, writes ~/.agentium/env.conf
│   ├── install-voice-bridge.sh  # Phase 2+3 — venv, deps, service registration
│   └── uninstall-voice-bridge.sh
│
├── backend/
│   ├── api/routes/auth.py       # +POST /auth/voice-token, GET /auth/verify-session
│   └── core/voice_auth.py       # voice-scoped JWT helper
│
├── frontend/src/
│   ├── services/voiceBridge.ts  # Browser WS client
│   ├── hooks/useVoiceBridge.ts  # React hook
│   └── components/
│       └── VoiceIndicator.tsx   # Status badge in MainLayout
│
├── .env.example                 # +VOICE_JWT_SECRET, VOICE_TOKEN_DURATION_MINUTES
├── docker-compose.yml           # +host-setup init service
└── Makefile                     # +install-voice, uninstall-voice, voice-logs
```

---

## 3. Phase 1 — OS Detection

**`scripts/detect-host.sh`**

```bash
#!/usr/bin/env bash
# =============================================================================
# detect-host.sh  — Agentium OS probe
# Writes ~/.agentium/env.conf  (KEY=VALUE pairs consumed by installer + bridge)
# Every check is independent: a failure writes a safe default and warns.
# =============================================================================
set -euo pipefail

CONF_DIR="$HOME/.agentium"
CONF_FILE="$CONF_DIR/env.conf"
LOG_FILE="$CONF_DIR/detect.log"
WARN_COUNT=0

mkdir -p "$CONF_DIR"
: > "$CONF_FILE"          # truncate / create
: > "$LOG_FILE"

# ── helpers ──────────────────────────────────────────────────────────────────

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
conf() { echo "$1=$2" >> "$CONF_FILE"; }       # write a key=value pair
safe_conf() {                                  # write a key=value, warn if value empty
  local key="$1" val="$2" fallback="$3"
  if [[ -z "$val" ]]; then
    warn "Could not detect $key — using fallback: $fallback"
    conf "$key" "$fallback"
  else
    conf "$key" "$val"
  fi
}

log "=== Agentium OS Detection Started ==="

# ── Step 1.1  OS family ───────────────────────────────────────────────────────
log "Step 1.1 — Detecting OS family"
detect_os_family() {
  local uname
  uname=$(uname -s 2>/dev/null) || { warn "uname failed; defaulting to linux"; echo "linux"; return; }
  case "$uname" in
    Darwin)  echo "macos"  ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl2"
      else
        echo "linux"
      fi
      ;;
    MINGW*|CYGWIN*) echo "wsl2" ;;
    *) warn "Unknown OS '$uname'; defaulting to linux"; echo "linux" ;;
  esac
}
OS_FAMILY=$(detect_os_family)
conf "OS_FAMILY" "$OS_FAMILY"
log "  OS_FAMILY=$OS_FAMILY"

# ── Step 1.2  Linux distro ────────────────────────────────────────────────────
log "Step 1.2 — Detecting Linux distro"
DISTRO="unknown"
if [[ "$OS_FAMILY" == "linux" || "$OS_FAMILY" == "wsl2" ]]; then
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release 2>/dev/null || warn "/etc/os-release source failed"
    DISTRO="${ID:-unknown}"
  else
    warn "/etc/os-release not found — distro detection skipped"
  fi
fi
conf "DISTRO" "$DISTRO"
log "  DISTRO=$DISTRO"

# ── Step 1.3  Package manager ─────────────────────────────────────────────────
log "Step 1.3 — Selecting package manager"
detect_pkg_mgr() {
  case "$OS_FAMILY" in
    macos)  command -v brew &>/dev/null && echo "brew" || { warn "Homebrew not found — install from brew.sh first"; echo "brew_missing"; } ;;
    linux|wsl2)
      case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)  echo "apt" ;;
        fedora|rhel|centos|rocky)     echo "dnf" ;;
        arch|manjaro|endeavouros)     echo "pacman" ;;
        opensuse*)                    echo "zypper" ;;
        *)
          # last-resort: probe binaries
          for mgr in apt dnf pacman zypper; do
            command -v "$mgr" &>/dev/null && { echo "$mgr"; return; }
          done
          warn "No known package manager found; manual install required"
          echo "unknown"
          ;;
      esac
      ;;
    *) warn "Cannot determine package manager for OS_FAMILY=$OS_FAMILY"; echo "unknown" ;;
  esac
}
PKG_MGR=$(detect_pkg_mgr)
conf "PKG_MGR" "$PKG_MGR"
log "  PKG_MGR=$PKG_MGR"

# ── Step 1.4  Python version ──────────────────────────────────────────────────
log "Step 1.4 — Checking Python ≥ 3.10"
detect_python() {
  for bin in python3.12 python3.11 python3.10 python3; do
    if command -v "$bin" &>/dev/null; then
      local ver
      ver=$("$bin" -c "import sys; print(sys.version_info[:2])" 2>/dev/null) || continue
      # ver looks like "(3, 11)"
      local major minor
      major=$(echo "$ver" | tr -d '(),' | awk '{print $1}')
      minor=$(echo "$ver" | tr -d '(),' | awk '{print $2}')
      if (( major >= 3 && minor >= 10 )); then
        echo "$bin"
        return
      fi
    fi
  done
  warn "No Python ≥ 3.10 found. Bridge STT/TTS will not function. Install Python 3.10+ and re-run."
  echo "python3_missing"
}
PYTHON_BIN=$(detect_python)
conf "PYTHON_BIN" "$PYTHON_BIN"
log "  PYTHON_BIN=$PYTHON_BIN"

# ── Step 1.5  PortAudio ───────────────────────────────────────────────────────
log "Step 1.5 — Checking PortAudio"
PORTAUDIO_INSTALLED="false"
check_portaudio() {
  case "$OS_FAMILY" in
    macos)  [[ -d /opt/homebrew/include/portaudio* ]] || [[ -d /usr/local/include/portaudio* ]] && echo "true" || echo "false" ;;
    *)
      pkg-config --exists portaudio-2.0 2>/dev/null && echo "true" || echo "false"
      ;;
  esac
}
PORTAUDIO_INSTALLED=$(check_portaudio 2>/dev/null || echo "false")
if [[ "$PORTAUDIO_INSTALLED" == "false" ]]; then
  warn "PortAudio not found — installer will attempt to install it"
fi
conf "PORTAUDIO_INSTALLED" "$PORTAUDIO_INSTALLED"
log "  PORTAUDIO_INSTALLED=$PORTAUDIO_INSTALLED"

# ── Step 1.6  Service manager ─────────────────────────────────────────────────
log "Step 1.6 — Detecting service manager"
detect_svc_mgr() {
  case "$OS_FAMILY" in
    macos)  command -v launchctl &>/dev/null && echo "launchd" || { warn "launchctl missing"; echo "manual"; } ;;
    linux)  systemctl --user status &>/dev/null 2>&1 && echo "systemd" || { warn "systemd --user not available; will use manual startup"; echo "manual"; } ;;
    wsl2)   echo "wsl2" ;;
    *)      warn "Unknown OS for service manager"; echo "manual" ;;
  esac
}
SVC_MGR=$(detect_svc_mgr)
conf "SVC_MGR" "$SVC_MGR"
log "  SVC_MGR=$SVC_MGR"

# ── Step 1.7  Docker gateway IP ───────────────────────────────────────────────
log "Step 1.7 — Probing Docker gateway IP"
detect_backend_host() {
  # Try host.docker.internal first (Docker Desktop / newer Linux)
  if ping -c1 -W1 host.docker.internal &>/dev/null 2>&1; then
    echo "host.docker.internal"
    return
  fi
  # Try docker0 interface
  local ip
  ip=$(ip route 2>/dev/null | awk '/docker0/ {print $9; exit}')
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  # Try default gateway on docker0 subnet
  ip=$(ip addr show docker0 2>/dev/null | awk '/inet / {split($2,a,"/"); print a[1]}')
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  warn "Cannot auto-detect Docker gateway. Defaulting to 172.17.0.1 — edit ~/.agentium/env.conf if wrong."
  echo "172.17.0.1"
}
BACKEND_HOST=$(detect_backend_host)
conf "BACKEND_HOST" "$BACKEND_HOST"
conf "BACKEND_PORT" "8000"
conf "BRIDGE_WS_PORT" "9999"
log "  BACKEND_HOST=$BACKEND_HOST"

# ── Step 1.8  Microphone check ────────────────────────────────────────────────
log "Step 1.8 — Checking for microphone"
HAS_MIC="false"
check_mic() {
  case "$OS_FAMILY" in
    macos)
      system_profiler SPAudioDataType 2>/dev/null | grep -qi "microphone" && echo "true" || echo "false"
      ;;
    linux|wsl2)
      # arecord -l lists capture devices; non-zero exit means none
      if command -v arecord &>/dev/null; then
        arecord -l 2>/dev/null | grep -q "card" && echo "true" || echo "false"
      else
        # fall back to /proc/asound
        ls /proc/asound/card*/pcm*c 2>/dev/null | head -1 | grep -q pcm && echo "true" || echo "false"
      fi
      ;;
    *) echo "unknown" ;;
  esac
}
HAS_MIC=$(check_mic 2>/dev/null || echo "unknown")
if [[ "$HAS_MIC" == "false" ]]; then
  warn "No microphone detected. Voice capture will fail at runtime — connect a mic and restart the bridge."
fi
conf "HAS_MIC" "$HAS_MIC"
conf "VENV_PATH" "$HOME/.agentium-voice"
log "  HAS_MIC=$HAS_MIC"

# ── Summary ───────────────────────────────────────────────────────────────────
log "=== Detection complete. $WARN_COUNT warning(s). Config written to $CONF_FILE ==="
if (( WARN_COUNT > 0 )); then
  echo ""
  echo "⚠  $WARN_COUNT warning(s) during detection. Review $LOG_FILE for details."
  echo "   Non-critical warnings are safe to ignore; the installer will handle them."
  echo ""
fi
cat "$CONF_FILE"
```

---

## 4. Phase 2 — Dependency Installer

**`scripts/install-voice-bridge.sh`**

```bash
#!/usr/bin/env bash
# =============================================================================
# install-voice-bridge.sh  — Agentium Voice Bridge Installer
# Reads ~/.agentium/env.conf  produced by detect-host.sh
# Every step has its own error handler — a failure warns and continues.
# =============================================================================
set -uo pipefail     # -e intentionally OFF: we handle errors per-step

CONF_FILE="$HOME/.agentium/env.conf"
LOG_FILE="$HOME/.agentium/install.log"
WARN_COUNT=0
FAIL_COUNT=0

# ── helpers ──────────────────────────────────────────────────────────────────
log()   { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn()  { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
fail()  { echo "[ERROR] $*" | tee -a "$LOG_FILE" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }
ok()    { echo "[OK]    $*" | tee -a "$LOG_FILE"; }
step()  { echo "" | tee -a "$LOG_FILE"; echo "──── $* ────" | tee -a "$LOG_FILE"; }

# run a command; on non-zero exit: warn and return 1 (caller decides whether fatal)
run_or_warn() {
  local label="$1"; shift
  if "$@" >> "$LOG_FILE" 2>&1; then
    ok "$label"
    return 0
  else
    warn "$label failed (exit $?). See $LOG_FILE for details. Continuing."
    return 1
  fi
}

# ── Load config ───────────────────────────────────────────────────────────────
if [[ ! -f "$CONF_FILE" ]]; then
  echo "[ERROR] $CONF_FILE not found. Run scripts/detect-host.sh first."
  exit 1
fi
# shellcheck disable=SC1090
source "$CONF_FILE"
: > "$LOG_FILE"
log "=== Agentium Voice Bridge Installer ==="
log "Loaded config from $CONF_FILE"

VENV="${VENV_PATH:-$HOME/.agentium-voice}"
PYTHON="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_DIR="$(dirname "$SCRIPT_DIR")/voice-bridge"

# ── Step 2.1  System packages ─────────────────────────────────────────────────
step "2.1  Installing system packages"
install_system_packages() {
  case "${PKG_MGR:-unknown}" in
    apt)
      run_or_warn "apt update" sudo apt-get update -qq || true
      run_or_warn "apt install audio libs" \
        sudo apt-get install -y -qq python3-dev portaudio19-dev libespeak-ng1 ffmpeg alsa-utils
      ;;
    dnf)
      run_or_warn "dnf install audio libs" \
        sudo dnf install -y -q python3-devel portaudio-devel espeak-ng ffmpeg
      ;;
    pacman)
      run_or_warn "pacman install audio libs" \
        sudo pacman -S --noconfirm --needed python portaudio espeak-ng ffmpeg
      ;;
    brew)
      run_or_warn "brew install portaudio" brew install portaudio
      ;;
    brew_missing)
      warn "Homebrew not installed. Visit https://brew.sh — then re-run this script."
      ;;
    unknown|*)
      warn "Unknown package manager '${PKG_MGR:-}'. Skipping system package install."
      warn "Manually install: portaudio-dev, espeak-ng, ffmpeg, python3-dev"
      ;;
  esac
}
install_system_packages

# ── Step 2.2  Python venv ─────────────────────────────────────────────────────
step "2.2  Creating Python venv at $VENV"
if [[ "${PYTHON_BIN:-python3_missing}" == "python3_missing" ]]; then
  warn "Python ≥ 3.10 not found — skipping venv creation. Bridge will not function."
else
  if [[ -d "$VENV" ]]; then
    log "  Existing venv found at $VENV — upgrading in place (idempotent)"
  else
    run_or_warn "Create venv" "$PYTHON" -m venv "$VENV" || {
      fail "Could not create venv at $VENV. Bridge will not function."
    }
  fi
fi

# ── Step 2.3  pip install ─────────────────────────────────────────────────────
step "2.3  Installing Python packages"
REQUIREMENTS="$BRIDGE_DIR/requirements.txt"
if [[ ! -f "$REQUIREMENTS" ]]; then
  warn "requirements.txt not found at $REQUIREMENTS — writing defaults"
  mkdir -p "$BRIDGE_DIR"
  cat > "$REQUIREMENTS" <<EOF
websockets>=12.0
SpeechRecognition>=3.10
pyttsx3>=2.90
PyAudio>=0.2.14
vosk>=0.3.45
requests>=2.31
PyJWT>=2.8
EOF
fi

if [[ -x "$VENV/bin/pip" ]]; then
  run_or_warn "pip upgrade" "$VENV/bin/pip" install --quiet --upgrade pip
  # Install each package individually so one failure doesn't abort the rest
  while IFS= read -r pkg || [[ -n "$pkg" ]]; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    if run_or_warn "pip install $pkg" "$VENV/bin/pip" install --quiet "$pkg"; then
      ok "  Installed: $pkg"
    else
      warn "  Could not install $pkg — some voice features may be degraded."
    fi
  done < "$REQUIREMENTS"
else
  warn "pip not found in venv. Skipping Python package install."
fi

# ── Step 2.4  Copy bridge source ──────────────────────────────────────────────
step "2.4  Copying bridge source to venv"
if [[ -f "$BRIDGE_DIR/main.py" ]]; then
  cp "$BRIDGE_DIR/main.py" "$VENV/main.py" && ok "main.py copied" || warn "Could not copy main.py — service will use source path instead"
fi

# ── Step 2.5  Write env.conf additions ───────────────────────────────────────
step "2.5  Finalising env.conf"
{
  echo "VENV_PATH=$VENV"
  echo "BRIDGE_MAIN=$VENV/main.py"
  echo "INSTALL_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$CONF_FILE"
ok "env.conf updated"

# ── Step 2.6  Summary ─────────────────────────────────────────────────────────
echo ""
if (( FAIL_COUNT > 0 )); then
  echo "⛔  Install finished with $FAIL_COUNT fatal error(s) and $WARN_COUNT warning(s)."
  echo "   Voice bridge may not function correctly. Review $LOG_FILE"
elif (( WARN_COUNT > 0 )); then
  echo "⚠   Install finished with $WARN_COUNT warning(s) — non-critical, continuing."
  echo "   Review $LOG_FILE for details."
else
  echo "✅  Install complete — no warnings."
fi

# Always continue to service registration regardless of warnings
bash "$(dirname "${BASH_SOURCE[0]}")/register-service.sh"
```

**`voice-bridge/requirements.txt`**

```
websockets>=12.0
SpeechRecognition>=3.10
pyttsx3>=2.90
PyAudio>=0.2.14
vosk>=0.3.45
requests>=2.31
PyJWT>=2.8
```

---

## 5. Phase 3 — Service Registration

**`scripts/register-service.sh`** (called at the end of the installer)

```bash
#!/usr/bin/env bash
# =============================================================================
# register-service.sh  — Registers agentium-voice as a background service
# Reads SVC_MGR from env.conf and branches to the correct method.
# Failures warn but never abort — bridge can always be started manually.
# =============================================================================
set -uo pipefail

CONF_FILE="$HOME/.agentium/env.conf"
LOG_FILE="$HOME/.agentium/install.log"
WARN_COUNT=0

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
ok()   { echo "[OK]    $*" | tee -a "$LOG_FILE"; }

# shellcheck disable=SC1090
source "$CONF_FILE" 2>/dev/null || { warn "Could not source $CONF_FILE"; }

VENV="${VENV_PATH:-$HOME/.agentium-voice}"
BRIDGE_MAIN="${BRIDGE_MAIN:-$VENV/main.py}"
PYTHON_EXE="$VENV/bin/python"

# ── 3a  systemd ───────────────────────────────────────────────────────────────
register_systemd() {
  local unit_dir="$HOME/.config/systemd/user"
  local unit_file="$unit_dir/agentium-voice.service"
  mkdir -p "$unit_dir"

  cat > "$unit_file" <<EOF
[Unit]
Description=Agentium Voice Bridge
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON_EXE $BRIDGE_MAIN
Restart=on-failure
RestartSec=5
EnvironmentFile=$HOME/.agentium/env.conf

[Install]
WantedBy=default.target
EOF

  if systemctl --user daemon-reload 2>/dev/null; then
    ok "systemd daemon-reload"
  else
    warn "daemon-reload failed — run manually: systemctl --user daemon-reload"
  fi

  if systemctl --user enable --now agentium-voice 2>/dev/null; then
    ok "agentium-voice enabled and started"
  else
    warn "Could not enable/start agentium-voice — start manually:"
    warn "  systemctl --user start agentium-voice"
  fi
}

# ── 3b  launchd ───────────────────────────────────────────────────────────────
register_launchd() {
  local plist_dir="$HOME/Library/LaunchAgents"
  local plist_file="$plist_dir/com.agentium.voice.plist"
  mkdir -p "$plist_dir"

  # Unload existing if present (idempotent upgrade)
  if [[ -f "$plist_file" ]]; then
    launchctl unload "$plist_file" 2>/dev/null || true
    ok "Unloaded existing launchd job (upgrading)"
  fi

  cat > "$plist_file" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.agentium.voice</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_EXE</string>
    <string>$BRIDGE_MAIN</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>$HOME/.agentium/voice-bridge.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.agentium/voice-bridge.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>VENV_PATH</key>       <string>$VENV</string>
    <key>BACKEND_HOST</key>    <string>${BACKEND_HOST:-172.17.0.1}</string>
    <key>BACKEND_PORT</key>    <string>${BACKEND_PORT:-8000}</string>
    <key>BRIDGE_WS_PORT</key>  <string>${BRIDGE_WS_PORT:-9999}</string>
  </dict>
</dict>
</plist>
EOF

  if launchctl load "$plist_file" 2>/dev/null; then
    ok "launchd job loaded: com.agentium.voice"
  else
    warn "launchctl load failed. Try: launchctl load $plist_file"
  fi
}

# ── 3c  WSL2 shim ─────────────────────────────────────────────────────────────
register_wsl2() {
  local startup_script="$HOME/.agentium/start-voice.sh"

  cat > "$startup_script" <<EOF
#!/usr/bin/env bash
# WSL2 Voice Bridge Startup — sourced by Windows Task Scheduler
source "$HOME/.agentium/env.conf" 2>/dev/null || true
exec "$PYTHON_EXE" "$BRIDGE_MAIN" >> "$HOME/.agentium/voice-bridge.log" 2>&1
EOF
  chmod +x "$startup_script"
  ok "WSL2 startup script written: $startup_script"

  # Attempt to register a Windows scheduled task via powershell.exe
  local task_cmd
  task_cmd='schtasks /Create /F /TN "AgentiumVoiceBridge" /TR "wsl.exe -e bash '"$startup_script"'" /SC ONLOGON /RL LIMITED'
  if command -v powershell.exe &>/dev/null; then
    if powershell.exe -Command "$task_cmd" >> "$LOG_FILE" 2>&1; then
      ok "Windows Task Scheduler entry created"
    else
      warn "Could not create scheduled task automatically."
      warn "Run in PowerShell (as user): $task_cmd"
    fi
  else
    warn "powershell.exe not accessible from WSL2. Register the task manually:"
    warn "  $task_cmd"
  fi

  echo ""
  echo "  ℹ  WSL2 audio note: ensure WSLg or PulseAudio bridge is active."
  echo "     Check: pactl list sources | grep -i micro"
}

# ── 3d  Manual fallback ───────────────────────────────────────────────────────
register_manual() {
  warn "No supported service manager found (SVC_MGR=${SVC_MGR:-unknown})"
  warn "Start the bridge manually with:"
  warn "  $PYTHON_EXE $BRIDGE_MAIN"
  local rc_file=""
  [[ -f "$HOME/.zshrc" ]]  && rc_file="$HOME/.zshrc"
  [[ -f "$HOME/.bashrc" ]] && rc_file="$HOME/.bashrc"
  if [[ -n "$rc_file" ]]; then
    warn "Or add to $rc_file:"
    warn "  nohup $PYTHON_EXE $BRIDGE_MAIN &>/dev/null &"
  fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
log "=== Service Registration (SVC_MGR=${SVC_MGR:-unknown}) ==="
case "${SVC_MGR:-unknown}" in
  systemd) register_systemd ;;
  launchd) register_launchd ;;
  wsl2)    register_wsl2    ;;
  *)       register_manual  ;;
esac

if (( WARN_COUNT > 0 )); then
  echo "⚠  $WARN_COUNT service-registration warning(s). Review $LOG_FILE"
else
  echo "✅  Service registered successfully."
fi
echo "   To start manually: $PYTHON_EXE $BRIDGE_MAIN"
```

---

## 6. Phase 4 — Backend Voice Token API

**`backend/core/voice_auth.py`**

```python
"""
voice_auth.py — Helper for creating and verifying voice-scoped JWTs.
All errors are caught and re-raised as HTTPException so FastAPI
returns clean 401/500 responses rather than unhandled 500s.
"""
import os
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger("agentium.voice_auth")

VOICE_SECRET   = os.getenv("VOICE_JWT_SECRET", "")
DURATION_MIN   = int(os.getenv("VOICE_TOKEN_DURATION_MINUTES", "30"))
ALGORITHM      = "HS256"


def _require_secret() -> str:
    """Return the voice JWT secret or raise a clear 500 with a log warning."""
    if not VOICE_SECRET:
        logger.warning(
            "VOICE_JWT_SECRET is not set in environment. "
            "Voice token issuance is disabled. Set the variable and restart."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice token service not configured. Contact your administrator.",
        )
    return VOICE_SECRET


def create_voice_token(user_id: str) -> tuple[str, datetime]:
    """
    Issue a short-lived voice-scoped JWT.
    Returns (token_string, expiry_datetime).
    Raises HTTPException on misconfiguration.
    """
    secret = _require_secret()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=DURATION_MIN)
    payload = {
        "sub":   user_id,
        "scope": "voice_command",
        "exp":   expires_at,
        "iat":   datetime.now(timezone.utc),
    }
    try:
        token = jwt.encode(payload, secret, algorithm=ALGORITHM)
        return token, expires_at
    except Exception as exc:
        logger.error("Failed to encode voice token: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not issue voice token.",
        ) from exc


def verify_voice_token(token: str) -> dict:
    """
    Decode and validate a voice-scoped JWT.
    Returns the payload dict.
    Raises HTTPException on any validation failure.
    """
    secret = _require_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Voice token has expired.")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid voice token received: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid voice token.")
    if payload.get("scope") != "voice_command":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Token scope is not 'voice_command'.")
    return payload
```

**Additions to `backend/api/routes/auth.py`**

```python
# ── append to existing auth.py ────────────────────────────────────────────────
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from backend.core.voice_auth import create_voice_token
from backend.api.dependencies.auth import get_current_user  # existing dep

import logging
logger = logging.getLogger("agentium.routes.auth")


class VoiceTokenResponse(BaseModel):
    voice_token: str
    expires_at:  datetime


class SessionVerifyResponse(BaseModel):
    user_id:    str
    expires_at: datetime


@router.post("/voice-token", response_model=VoiceTokenResponse)
async def issue_voice_token(current_user=Depends(get_current_user)):
    """
    Issue a 30-minute voice-scoped JWT.
    Called by the browser immediately after login to activate the host bridge.
    """
    try:
        token, expires_at = create_voice_token(str(current_user.id))
        return VoiceTokenResponse(voice_token=token, expires_at=expires_at)
    except HTTPException:
        raise   # already formatted
    except Exception as exc:
        logger.error("Unexpected error in /voice-token: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Voice token error.")


@router.get("/verify-session", response_model=SessionVerifyResponse)
async def verify_session(current_user=Depends(get_current_user)):
    """
    Called by the voice bridge to confirm the browser session is still live.
    Uses the same auth dependency as all other protected routes.
    """
    try:
        return SessionVerifyResponse(
            user_id=str(current_user.id),
            expires_at=current_user.token_expires,   # set by your existing auth middleware
        )
    except AttributeError:
        # token_expires may not exist on all user objects
        logger.warning("verify-session: current_user missing token_expires")
        from datetime import timezone, timedelta
        return SessionVerifyResponse(
            user_id=str(current_user.id),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
```

**.env.example additions**

```env
# ── Voice Bridge ──────────────────────────────────────────────────────────────
VOICE_JWT_SECRET=change-me-to-a-random-32-char-string
VOICE_TOKEN_DURATION_MINUTES=30
```

---

## 7. Phase 5 — Voice Bridge Core

**`voice-bridge/main.py`**

```python
"""
main.py  —  Agentium Host-Native Voice Bridge
SecureVoiceBridge:
  • Runs a WebSocket server on 127.0.0.1:9999 (browser auth gate)
  • Waits idle until the browser sends a valid auth_delegate message
  • Enters wake-word → STT → POST /chat → TTS loop
  • Syncs every exchange back to the browser (ChatPage updates)
  • Every sub-system failure is caught, logged, and continues gracefully
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import jwt
import requests
import websockets
from websockets.server import WebSocketServerProtocol

# ── optional audio imports — warn if missing, bridge still starts ─────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.warning("[WARN] SpeechRecognition not installed — STT unavailable. "
                    "Install: pip install SpeechRecognition PyAudio")

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("[WARN] pyttsx3 not installed — TTS (speaker playback) unavailable. "
                    "Install: pip install pyttsx3")

try:
    import vosk  # noqa: F401 — checked at model-load time below
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.info("[INFO] vosk not installed — offline STT fallback unavailable.")


# ── logging setup ─────────────────────────────────────────────────────────────
LOG_FILE = os.path.expanduser("~/.agentium/voice-bridge.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agentium.voice")

# ── config from env.conf (loaded as env vars by service manager) ──────────────
BACKEND_HOST   = os.getenv("BACKEND_HOST",   "172.17.0.1")
BACKEND_PORT   = os.getenv("BACKEND_PORT",   "8000")
BRIDGE_PORT    = int(os.getenv("BRIDGE_WS_PORT", "9999"))
VOICE_SECRET   = os.getenv("VOICE_JWT_SECRET", "")
BACKEND_URL    = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
WAKE_WORDS     = {"agentium", "hey agentium"}

# ── TTS engine (singleton, initialised once) ──────────────────────────────────
_tts_engine: Optional["pyttsx3.Engine"] = None
_tts_lock = threading.Lock()

def _get_tts() -> Optional["pyttsx3.Engine"]:
    global _tts_engine
    if not TTS_AVAILABLE:
        return None
    if _tts_engine is None:
        with _tts_lock:
            if _tts_engine is None:
                try:
                    _tts_engine = pyttsx3.init()
                    _tts_engine.setProperty("rate", 165)
                    log.info("TTS engine initialised")
                except Exception as exc:
                    log.warning("[WARN] Could not initialise TTS engine: %s — "
                                "replies will not be spoken aloud.", exc)
    return _tts_engine


def speak(text: str) -> None:
    """Speak text via host TTS. Silently skipped if engine unavailable."""
    engine = _get_tts()
    if engine is None:
        log.info("[TTS-SKIP] %s", text)
        return
    try:
        with _tts_lock:
            engine.say(text)
            engine.runAndWait()
    except Exception as exc:
        log.warning("[WARN] TTS playback failed: %s — continuing without audio.", exc)


# ── STT ───────────────────────────────────────────────────────────────────────
def transcribe_audio(timeout: int = 5, phrase_limit: int = 15) -> Optional[str]:
    """
    Capture one phrase from the microphone and return the transcription.
    Returns None on any error (caller decides what to do).
    Tries Google STT first; falls back to Vosk offline if network fails.
    """
    if not SR_AVAILABLE:
        log.warning("[WARN] SpeechRecognition unavailable — cannot capture audio.")
        return None

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            log.info("STT: listening (timeout=%ds, phrase_limit=%ds)…", timeout, phrase_limit)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
    except sr.WaitTimeoutError:
        log.info("STT: listen timed out — no speech detected.")
        return None
    except OSError as exc:
        log.warning("[WARN] Microphone error: %s — check mic connection.", exc)
        return None
    except Exception as exc:
        log.warning("[WARN] Unexpected STT capture error: %s", exc)
        return None

    # ── Try Google STT ────────────────────────────────────────────────────────
    try:
        text = recognizer.recognize_google(audio)
        log.info("STT (Google): %r", text)
        return text.strip()
    except sr.UnknownValueError:
        log.info("STT: speech not understood")
        return None
    except sr.RequestError as exc:
        log.warning("[WARN] Google STT unavailable: %s — trying offline Vosk.", exc)

    # ── Vosk offline fallback ─────────────────────────────────────────────────
    if VOSK_AVAILABLE:
        try:
            import vosk as vosk_mod
            model_path = os.path.expanduser("~/.agentium/vosk-model")
            if not os.path.isdir(model_path):
                log.warning("[WARN] Vosk model not found at %s. "
                            "Download from https://alphacephei.com/vosk/models", model_path)
                return None
            model = vosk_mod.Model(model_path)
            rec = vosk_mod.KaldiRecognizer(model, 16000)
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rec.AcceptWaveform(raw)
            result = json.loads(rec.Result())
            text = result.get("text", "").strip()
            log.info("STT (Vosk offline): %r", text)
            return text or None
        except Exception as exc:
            log.warning("[WARN] Vosk offline STT failed: %s", exc)

    return None


# ── Backend communication ─────────────────────────────────────────────────────
def post_to_chat(transcription: str, voice_token: str) -> Optional[str]:
    """
    POST transcription to /api/chat using the voice-scoped token.
    Returns the agent reply text, or None on any error.
    """
    url = f"{BACKEND_URL}/api/chat"
    headers = {
        "Authorization": f"Bearer {voice_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "message": transcription,
        "source":  "voice",
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Support multiple response shapes gracefully
        reply = (
            data.get("reply")
            or data.get("response")
            or data.get("message")
            or data.get("content")
            or str(data)
        )
        log.info("Chat response received (%d chars)", len(reply))
        return reply
    except requests.exceptions.ConnectionError:
        log.warning("[WARN] Cannot reach backend at %s — is Docker running?", BACKEND_URL)
    except requests.exceptions.Timeout:
        log.warning("[WARN] Backend request timed out after 30s.")
    except requests.exceptions.HTTPError as exc:
        log.warning("[WARN] Backend returned HTTP %s: %s", exc.response.status_code, exc)
    except Exception as exc:
        log.warning("[WARN] Unexpected error calling chat API: %s", exc)
    return None


def verify_session_with_backend(browser_jwt: str) -> bool:
    """
    Ask the backend to validate the browser's JWT.
    Returns True on 200, False on any error.
    """
    url = f"{BACKEND_URL}/api/auth/verify-session"
    headers = {"Authorization": f"Bearer {browser_jwt}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            log.info("Session verified with backend.")
            return True
        log.warning("[WARN] verify-session returned %d — rejecting bridge activation.",
                    response.status_code)
        return False
    except requests.exceptions.ConnectionError:
        log.warning("[WARN] Backend unreachable during verify-session. "
                    "Activating bridge in offline mode (reduced security).")
        return True   # degraded but continue — allows offline dev use
    except Exception as exc:
        log.warning("[WARN] verify-session error: %s — activating in offline mode.", exc)
        return True


# ── Main bridge class ─────────────────────────────────────────────────────────
class SecureVoiceBridge:
    """
    State machine:
      IDLE → (browser connects + auth) → WAITING_FOR_WAKE_WORD
           → (wake-word) → CAPTURING_COMMAND
           → (speech) → PROCESSING
           → (reply) → SPEAKING → WAITING_FOR_WAKE_WORD
           → (browser disconnects or token expires) → IDLE
    """

    IDLE                  = "idle"
    WAITING_FOR_WAKE_WORD = "waiting_for_wake_word"
    CAPTURING_COMMAND     = "capturing_command"
    PROCESSING            = "processing"
    SPEAKING              = "speaking"
    EXPIRED               = "expired"

    def __init__(self) -> None:
        self.state:        str                         = self.IDLE
        self.voice_token:  Optional[str]               = None
        self.browser_jwt:  Optional[str]               = None
        self.token_expires: Optional[datetime]         = None
        self._browser_ws:  Optional[WebSocketServerProtocol] = None
        self._stop_event   = asyncio.Event()
        self._listen_task: Optional[asyncio.Task]      = None

    # ── Token helpers ─────────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        if not self.voice_token or not self.token_expires:
            return False
        if datetime.now(timezone.utc) >= self.token_expires:
            log.info("Voice token has expired.")
            return False
        return True

    def _parse_expiry(self, expires_at: str) -> Optional[datetime]:
        """Parse ISO8601 string from the browser's auth_delegate message."""
        try:
            # Handle both Z and +00:00 suffixes
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return dt
        except (ValueError, AttributeError) as exc:
            log.warning("[WARN] Could not parse token expiry %r: %s — "
                        "defaulting to 30 minutes from now.", expires_at, exc)
            from datetime import timedelta
            return datetime.now(timezone.utc) + timedelta(minutes=30)

    # ── WebSocket server ──────────────────────────────────────────────────────

    async def handle_browser_ws(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a single browser WebSocket connection."""
        log.info("Browser connected from %s", websocket.remote_address)
        self._browser_ws = websocket

        try:
            async for raw_message in websocket:
                await self._process_browser_message(raw_message)
        except websockets.exceptions.ConnectionClosedOK:
            log.info("Browser WebSocket closed cleanly.")
        except websockets.exceptions.ConnectionClosedError as exc:
            log.warning("[WARN] Browser WebSocket closed with error: %s", exc)
        except Exception as exc:
            log.warning("[WARN] Unexpected browser WS error: %s", exc)
        finally:
            await self._on_browser_disconnect()

    async def _process_browser_message(self, raw: str) -> None:
        """Parse and dispatch a message from the browser."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("[WARN] Invalid JSON from browser: %s — ignoring.", exc)
            return

        msg_type = msg.get("type", "")

        if msg_type == "auth_delegate":
            await self._handle_auth_delegate(msg)
        elif msg_type == "logout":
            log.info("Browser sent logout — deactivating bridge.")
            await self._on_browser_disconnect()
        elif msg_type == "ping":
            await self._send_to_browser({"type": "pong"})
        else:
            log.info("Unknown browser message type %r — ignoring.", msg_type)

    async def _handle_auth_delegate(self, msg: dict) -> None:
        """Validate auth_delegate and activate listening if credentials are good."""
        browser_jwt  = msg.get("browserJwt",  "")
        voice_token  = msg.get("voiceToken",  "")
        expires_at   = msg.get("expiresAt",   "")

        if not browser_jwt or not voice_token:
            log.warning("[WARN] auth_delegate missing fields — ignoring.")
            await self._send_to_browser({
                "type": "auth_error",
                "detail": "Missing browserJwt or voiceToken in auth_delegate.",
            })
            return

        # Verify the browser's session JWT with the backend (non-blocking)
        session_ok = await asyncio.get_event_loop().run_in_executor(
            None, verify_session_with_backend, browser_jwt
        )
        if not session_ok:
            log.warning("[WARN] Backend rejected browser session — bridge stays idle.")
            await self._send_to_browser({
                "type": "auth_error",
                "detail": "Session verification failed. Please log in again.",
            })
            return

        # Locally decode voice token for expiry (no network call needed)
        if VOICE_SECRET:
            try:
                jwt.decode(voice_token, VOICE_SECRET, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                log.warning("[WARN] Voice token already expired — rejecting.")
                await self._send_to_browser({"type": "auth_error", "detail": "Voice token expired."})
                return
            except jwt.InvalidTokenError as exc:
                log.warning("[WARN] Voice token invalid: %s", exc)
                # Don't hard-reject — backend will catch invalid tokens on /chat calls
        else:
            log.warning("[WARN] VOICE_JWT_SECRET not set — skipping local token validation.")

        self.browser_jwt   = browser_jwt
        self.voice_token   = voice_token
        self.token_expires = self._parse_expiry(expires_at)
        self.state         = self.WAITING_FOR_WAKE_WORD

        log.info("Bridge activated. Listening for wake-word %r.", WAKE_WORDS)
        await self._send_to_browser({"type": "bridge_activated", "state": self.state})

        # Start the listen loop if not already running
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen_loop())

    async def _on_browser_disconnect(self) -> None:
        """Clear all auth state when the browser disconnects."""
        self.state         = self.IDLE
        self.voice_token   = None
        self.browser_jwt   = None
        self.token_expires = None
        self._browser_ws   = None
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        log.info("Bridge deactivated — back to idle.")

    async def _send_to_browser(self, payload: dict) -> None:
        """Send a JSON message to the browser. Silently skip if not connected."""
        if self._browser_ws is None:
            return
        try:
            await self._browser_ws.send(json.dumps(payload))
        except Exception as exc:
            log.warning("[WARN] Could not send message to browser: %s", exc)

    # ── Listen loop ───────────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """
        Main voice exchange loop. Runs in the background.
        Checks token validity before each action.
        Falls back gracefully on every possible failure.
        """
        log.info("Listen loop started.")
        while self.state != self.IDLE:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                log.info("Listen loop cancelled.")
                break
            except Exception as exc:
                log.warning("[WARN] Unexpected error in listen loop: %s — retrying in 2s.", exc)
                await asyncio.sleep(2)
        log.info("Listen loop exited.")

    async def _listen_once(self) -> None:
        """Execute one full wake-word → command → reply cycle."""
        # ── Token expiry check ────────────────────────────────────────────────
        if not self._token_valid():
            self.state = self.EXPIRED
            log.info("Token expired — notifying browser and going idle.")
            await self._send_to_browser({"type": "token_expired"})
            speak("Your session has expired. Please log in again to continue.")
            await self._on_browser_disconnect()
            return

        # ── Yield control so the WS server can run ────────────────────────────
        await asyncio.sleep(0.1)

        # ── Wake-word detection ───────────────────────────────────────────────
        if self.state != self.WAITING_FOR_WAKE_WORD:
            return

        transcription = await asyncio.get_event_loop().run_in_executor(
            None, transcribe_audio, 3, 4   # short timeout for wake-word polling
        )
        if transcription is None:
            return   # nothing heard, loop again

        if not any(w in transcription.lower() for w in WAKE_WORDS):
            log.info("STT heard %r but no wake-word — ignoring.", transcription)
            return

        # ── Command capture ───────────────────────────────────────────────────
        self.state = self.CAPTURING_COMMAND
        await self._send_to_browser({"type": "state_change", "state": self.state})
        speak("Yes, I'm listening.")

        command = await asyncio.get_event_loop().run_in_executor(
            None, transcribe_audio, 5, 15
        )
        if not command:
            log.info("No command heard after wake-word — returning to standby.")
            speak("I didn't catch that. Say 'Agentium' again when ready.")
            self.state = self.WAITING_FOR_WAKE_WORD
            await self._send_to_browser({"type": "state_change", "state": self.state})
            return

        log.info("Command captured: %r", command)
        await self._send_to_browser({"type": "transcription", "text": command})

        # ── Processing ────────────────────────────────────────────────────────
        self.state = self.PROCESSING
        await self._send_to_browser({"type": "state_change", "state": self.state})

        reply = await asyncio.get_event_loop().run_in_executor(
            None, post_to_chat, command, self.voice_token
        )
        if reply is None:
            log.warning("[WARN] No reply from backend — telling user and returning to standby.")
            speak("I'm having trouble reaching the backend right now. Please try again.")
            self.state = self.WAITING_FOR_WAKE_WORD
            await self._send_to_browser({"type": "state_change", "state": self.state})
            return

        # ── Speaking ──────────────────────────────────────────────────────────
        self.state = self.SPEAKING
        await self._send_to_browser({
            "type":   "voice_interaction",
            "user":   command,
            "reply":  reply,
        })
        speak(reply)

        self.state = self.WAITING_FOR_WAKE_WORD
        await self._send_to_browser({"type": "state_change", "state": self.state})

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the WebSocket server and run until stopped."""
        log.info("Starting voice bridge WS server on 127.0.0.1:%d", BRIDGE_PORT)
        try:
            async with websockets.serve(
                self.handle_browser_ws,
                "127.0.0.1",
                BRIDGE_PORT,
                ping_interval=20,
                ping_timeout=10,
            ):
                log.info("Voice bridge ready. Waiting for browser connection…")
                await asyncio.Future()   # run forever
        except OSError as exc:
            log.error("[ERROR] Cannot bind to port %d: %s", BRIDGE_PORT, exc)
            log.error("        Is another instance already running? "
                      "Check: lsof -i :%d", BRIDGE_PORT)
            raise
        except Exception as exc:
            log.error("[ERROR] Voice bridge server crashed: %s", exc, exc_info=True)
            raise


if __name__ == "__main__":
    bridge = SecureVoiceBridge()
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Voice bridge stopped by user (KeyboardInterrupt).")
    except Exception as exc:
        log.error("[ERROR] Fatal bridge error: %s", exc, exc_info=True)
        raise SystemExit(1)
```

---

## 8. Phase 6 — Frontend Integration

### `frontend/src/services/voiceBridge.ts`

```typescript
/**
 * voiceBridge.ts
 * Manages the browser-side WebSocket connection to the host voice bridge.
 * Errors are caught at every async boundary — a broken bridge never
 * crashes the rest of the app.
 */

import toast from "react-hot-toast";

const BRIDGE_URL = "ws://localhost:9999";
const VOICE_TOKEN_URL = "/api/auth/voice-token";
const RECONNECT_DELAY = 5_000; // ms between reconnect attempts
const MAX_RECONNECTS = 5;

export type BridgeStatus =
  | "idle"
  | "connecting"
  | "active"
  | "error"
  | "offline";

export interface VoiceInteractionEvent {
  type: "voice_interaction";
  user: string;
  reply: string;
}

type MessageHandler = (event: VoiceInteractionEvent) => void;

class VoiceBridgeService {
  private ws: WebSocket | null = null;
  private voiceToken: string = "";
  private browserJwt: string = "";
  private reconnectCount = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  public status: BridgeStatus = "idle";
  public bridgeState: string = "idle";

  private statusListeners: Array<(s: BridgeStatus) => void> = [];
  private messageListeners: MessageHandler[] = [];

  // ── Public API ────────────────────────────────────────────────────────────

  /** Called from useVoiceBridge after login. */
  async connect(jwt: string): Promise<void> {
    this.browserJwt = jwt;
    this.reconnectCount = 0;
    await this._fetchVoiceToken();
    this._openSocket();
  }

  /** Called on logout or app unmount. */
  disconnect(): void {
    this._clearReconnectTimer();
    if (this.ws) {
      try {
        this.ws.send(JSON.stringify({ type: "logout" }));
      } catch {
        /* ignore — socket may already be closed */
      }
      this.ws.close();
      this.ws = null;
    }
    this.voiceToken = "";
    this._setStatus("idle");
  }

  onStatusChange(cb: (s: BridgeStatus) => void): () => void {
    this.statusListeners.push(cb);
    return () => {
      this.statusListeners = this.statusListeners.filter((l) => l !== cb);
    };
  }

  onVoiceInteraction(cb: MessageHandler): () => void {
    this.messageListeners.push(cb);
    return () => {
      this.messageListeners = this.messageListeners.filter((l) => l !== cb);
    };
  }

  // ── Token fetching ────────────────────────────────────────────────────────

  private async _fetchVoiceToken(): Promise<void> {
    try {
      const response = await fetch(VOICE_TOKEN_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.browserJwt}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        // Not a fatal error — bridge will stay idle; warn user subtly
        console.warn(
          `[VoiceBridge] Could not fetch voice token (HTTP ${response.status}). ` +
            "Host voice will be unavailable.",
        );
        toast("Voice bridge unavailable — using browser-only mode.", {
          icon: "🎙️",
        });
        return;
      }

      const data = await response.json();
      this.voiceToken = data.voice_token ?? "";
      if (!this.voiceToken) {
        console.warn("[VoiceBridge] voice_token missing from response.");
      }
    } catch (err) {
      console.warn("[VoiceBridge] Failed to fetch voice token:", err);
      // Non-fatal: app continues without host voice
    }
  }

  // ── WebSocket lifecycle ───────────────────────────────────────────────────

  private _openSocket(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this._setStatus("connecting");
    let ws: WebSocket;

    try {
      ws = new WebSocket(BRIDGE_URL);
    } catch (err) {
      // Thrown synchronously if the URL is malformed
      console.warn("[VoiceBridge] Cannot construct WebSocket:", err);
      this._setStatus("offline");
      return;
    }

    ws.onopen = () => {
      console.info("[VoiceBridge] Connected to host bridge.");
      this.reconnectCount = 0;
      this._sendAuthDelegate(ws);
    };

    ws.onmessage = (event) => {
      this._handleMessage(event.data);
    };

    ws.onerror = (event) => {
      // onerror fires before onclose; just log — onclose handles reconnect
      console.warn("[VoiceBridge] WebSocket error:", event);
    };

    ws.onclose = (event) => {
      console.info(`[VoiceBridge] Disconnected (code=${event.code}).`);
      this.ws = null;

      if (this.status === "idle") return; // intentional disconnect

      if (this.reconnectCount < MAX_RECONNECTS) {
        this.reconnectCount++;
        console.info(
          `[VoiceBridge] Reconnecting in ${RECONNECT_DELAY / 1000}s ` +
            `(attempt ${this.reconnectCount}/${MAX_RECONNECTS})…`,
        );
        this._setStatus("connecting");
        this.reconnectTimer = setTimeout(
          () => this._openSocket(),
          RECONNECT_DELAY,
        );
      } else {
        console.warn(
          "[VoiceBridge] Max reconnect attempts reached — bridge offline.",
        );
        this._setStatus("offline");
        toast(
          "Host voice bridge is offline. Chat will continue in text mode.",
          { icon: "⚠️" },
        );
      }
    };

    this.ws = ws;
  }

  private _sendAuthDelegate(ws: WebSocket): void {
    if (!this.voiceToken) {
      // No voice token — still connected but bridge stays idle server-side
      this._setStatus("active"); // connected, but voice inactive
      return;
    }
    try {
      ws.send(
        JSON.stringify({
          type: "auth_delegate",
          browserJwt: this.browserJwt,
          voiceToken: this.voiceToken,
          expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        }),
      );
    } catch (err) {
      console.warn("[VoiceBridge] Failed to send auth_delegate:", err);
    }
  }

  // ── Message handling ──────────────────────────────────────────────────────

  private _handleMessage(raw: string): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(raw);
    } catch {
      console.warn("[VoiceBridge] Non-JSON message from bridge:", raw);
      return;
    }

    const type = msg["type"] as string | undefined;

    switch (type) {
      case "bridge_activated":
        this._setStatus("active");
        break;
      case "voice_interaction":
        this.messageListeners.forEach((cb) => {
          try {
            cb(msg as unknown as VoiceInteractionEvent);
          } catch (err) {
            console.warn("[VoiceBridge] voice_interaction handler error:", err);
          }
        });
        break;
      case "state_change":
        this.bridgeState = (msg["state"] as string) ?? "idle";
        break;
      case "token_expired":
        toast("Voice session expired. Log in again to re-activate.", {
          icon: "🔑",
        });
        this._setStatus("idle");
        break;
      case "auth_error":
        console.warn("[VoiceBridge] Auth error from bridge:", msg["detail"]);
        toast(`Voice bridge: ${msg["detail"] ?? "auth error"}`, { icon: "⚠️" });
        this._setStatus("error");
        break;
      case "pong":
        break; // keepalive, no action needed
      default:
        console.debug("[VoiceBridge] Unhandled message type:", type);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private _setStatus(status: BridgeStatus): void {
    this.status = status;
    this.statusListeners.forEach((cb) => {
      try {
        cb(status);
      } catch {
        /* ignore */
      }
    });
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

export const voiceBridgeService = new VoiceBridgeService();
```

### `frontend/src/hooks/useVoiceBridge.ts`

```typescript
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import {
  voiceBridgeService,
  BridgeStatus,
  VoiceInteractionEvent,
} from "@/services/voiceBridge";

interface UseVoiceBridgeReturn {
  status: BridgeStatus;
  bridgeState: string;
  lastTranscription: string;
}

export function useVoiceBridge(
  onVoiceInteraction?: (e: VoiceInteractionEvent) => void,
): UseVoiceBridgeReturn {
  const { user } = useAuthStore();
  const [status, setStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [bridgeState, setBridgeState] = useState(
    voiceBridgeService.bridgeState,
  );
  const [lastTranscription, setLast] = useState("");

  // Connect / disconnect when auth state changes
  useEffect(() => {
    if (user?.isAuthenticated && user.token) {
      voiceBridgeService.connect(user.token).catch((err) => {
        // connect() catches internally, but just in case
        console.warn("[useVoiceBridge] connect() threw:", err);
      });
    } else {
      voiceBridgeService.disconnect();
    }
    return () => voiceBridgeService.disconnect();
  }, [user?.isAuthenticated, user?.token]);

  // Subscribe to status changes
  useEffect(() => {
    const unsub = voiceBridgeService.onStatusChange(setStatus);
    return unsub;
  }, []);

  // Subscribe to voice_interaction events
  useEffect(() => {
    const unsub = voiceBridgeService.onVoiceInteraction((event) => {
      setLast(event.user);
      // Update bridgeState optimistically
      setBridgeState("waiting_for_wake_word");
      onVoiceInteraction?.(event);
    });
    return unsub;
  }, [onVoiceInteraction]);

  return { status, bridgeState, lastTranscription };
}
```

### `frontend/src/components/VoiceIndicator.tsx`

```tsx
import { Mic, MicOff, Loader2 } from "lucide-react";
import { BridgeStatus } from "@/services/voiceBridge";

interface Props {
  status: BridgeStatus;
  bridgeState: string;
}

const CONFIG: Record<
  BridgeStatus,
  { label: string; color: string; pulse: boolean }
> = {
  idle: { label: "Voice Idle", color: "text-gray-400", pulse: false },
  connecting: { label: "Connecting…", color: "text-yellow-400", pulse: true },
  active: { label: "Listening", color: "text-green-400", pulse: true },
  error: { label: "Bridge Error", color: "text-red-400", pulse: false },
  offline: { label: "Bridge Offline", color: "text-gray-500", pulse: false },
};

export function VoiceIndicator({ status, bridgeState }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.offline;
  const label =
    bridgeState === "processing"
      ? "Processing…"
      : bridgeState === "speaking"
        ? "Speaking…"
        : cfg.label;

  return (
    <div
      className={`flex items-center gap-1.5 text-xs font-medium ${cfg.color}`}
      title={`Voice bridge: ${label}`}
    >
      {status === "connecting" ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : status === "offline" || status === "error" ? (
        <MicOff className="w-3.5 h-3.5" />
      ) : (
        <span className="relative flex h-2 w-2">
          {cfg.pulse && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                status === "active" ? "bg-green-400" : "bg-yellow-400"
              }`}
            />
          )}
          <Mic className="w-3.5 h-3.5" />
        </span>
      )}
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}
```

### ChatPage additions (`ChatPage.tsx`)

```tsx
// Add inside ChatPage, alongside existing message handling:
import { useVoiceBridge } from "@/hooks/useVoiceBridge";
import { VoiceInteractionEvent } from "@/services/voiceBridge";

// Inside the component:
const handleVoiceInteraction = useCallback(
  (event: VoiceInteractionEvent) => {
    try {
      // Append the voice exchange to the existing chat history
      appendMessage({ role: "user", content: event.user, source: "voice" });
      appendMessage({
        role: "assistant",
        content: event.reply,
        source: "voice",
      });
    } catch (err) {
      console.warn("[ChatPage] Failed to append voice interaction:", err);
    }
  },
  [appendMessage],
);

const { status: bridgeStatus, bridgeState } = useVoiceBridge(
  handleVoiceInteraction,
);
```

---

## 9. Phase 7 — Docker Compose Wiring

**Additions to `docker-compose.yml`**

```yaml
services:
  # ── Voice Bridge Host Setup (one-shot, voice profile only) ──────────────────
  host-setup:
    image: ubuntu:22.04
    network_mode: host
    profiles: [voice]
    volumes:
      - ./scripts:/scripts:ro
      - ./voice-bridge:/voice-bridge:ro
      - ~/.agentium:/root/.agentium
      - ~/.agentium-voice:/root/.agentium-voice
    environment:
      - HOME=/root
    command: >
      bash -c "
        echo '[host-setup] Starting OS detection...' &&
        bash /scripts/detect-host.sh &&
        echo '[host-setup] Starting dependency install...' &&
        bash /scripts/install-voice-bridge.sh &&
        echo '[host-setup] Done.'
      "
    restart: "no"
```

**`.env.example` additions**

```env
# ── Voice Bridge ───────────────────────────────────────────
VOICE_JWT_SECRET=change-me-to-a-random-32-character-string
VOICE_TOKEN_DURATION_MINUTES=30
WHATSAPP_BRIDGE_TOKEN=changeme
```

**`Makefile` additions**

```makefile
.PHONY: install-voice uninstall-voice voice-logs voice-status

install-voice:
	@echo "Running host-native voice bridge installer..."
	docker compose --profile voice up host-setup --abort-on-container-exit
	@echo "Done. Check ~/.agentium/install.log for details."

uninstall-voice:
	@bash scripts/uninstall-voice-bridge.sh

voice-logs:
	@case "$$(grep SVC_MGR ~/.agentium/env.conf | cut -d= -f2)" in \
	  systemd) journalctl --user -u agentium-voice -f ;; \
	  launchd)  tail -f ~/.agentium/voice-bridge.log ;; \
	  *)        tail -f ~/.agentium/voice-bridge.log ;; \
	esac

voice-status:
	@case "$$(grep SVC_MGR ~/.agentium/env.conf | cut -d= -f2)" in \
	  systemd) systemctl --user status agentium-voice ;; \
	  launchd)  launchctl list com.agentium.voice ;; \
	  wsl2)     ps aux | grep agentium-voice ;; \
	  *)        echo "Run manually: ps aux | grep main.py" ;; \
	esac
```

---

## 10. Error Handling Reference

Every layer has its own error boundary. The table below shows what happens in each failure scenario so you know the system never silently breaks.

| Layer                     | Failure                         | What Happens                                       | User Impact                                                    |
| ------------------------- | ------------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| `detect-host.sh`          | `uname` fails                   | Defaults to `linux`, logs `[WARN]`                 | Detection continues with safe fallback                         |
| `detect-host.sh`          | No Python ≥ 3.10                | Writes `PYTHON_BIN=python3_missing`, warns         | Installer skips venv creation; shows clear message             |
| `detect-host.sh`          | No microphone                   | Sets `HAS_MIC=false`, warns                        | Bridge starts; tells user at runtime when speech capture fails |
| `detect-host.sh`          | Docker gateway unknown          | Defaults to `172.17.0.1`, warns                    | User can edit `~/.agentium/env.conf` to correct                |
| `install-voice-bridge.sh` | `apt`/`brew` fails              | `run_or_warn` logs and continues                   | Individual packages may be missing; warned in log              |
| `install-voice-bridge.sh` | One pip package fails           | Warned per-package; rest install                   | Degraded feature (e.g. no Vosk offline fallback)               |
| `register-service.sh`     | `systemctl` fails               | Warns with manual start command                    | User starts bridge manually                                    |
| `register-service.sh`     | `launchctl` fails               | Warns with manual load command                     | User loads plist manually                                      |
| `main.py` import          | `pyttsx3` missing               | `TTS_AVAILABLE=False`, warns once                  | Bridge runs; replies printed to log, not spoken                |
| `main.py` import          | `SpeechRecognition` missing     | `SR_AVAILABLE=False`, warns once                   | Bridge runs; no voice capture; text chat unaffected            |
| `main.py`                 | Mic error (`OSError`)           | Warns with message, returns `None`                 | Loop skips capture; tries again next cycle                     |
| `main.py`                 | Google STT network error        | Falls back to Vosk; warns if Vosk also unavailable | Returns `None`; bridge tells user it didn't hear               |
| `main.py`                 | Backend `ConnectionError`       | Warns, returns `None` to listen loop               | Bridge speaks "having trouble reaching backend"                |
| `main.py`                 | Backend HTTP error              | Warns with status code, continues                  | Same as above                                                  |
| `main.py`                 | TTS engine crash                | Warns, returns without speaking                    | Reply shown in ChatPage only                                   |
| `main.py`                 | Browser WS message invalid JSON | Logs warning, ignores message                      | Other messages unaffected                                      |
| `main.py`                 | Port 9999 already in use        | Logs `[ERROR]` with hint, raises                   | User sees clear message; no silent hang                        |
| `voiceBridge.ts`          | `/auth/voice-token` fails       | Warns in console, shows toast                      | App continues in text-only mode                                |
| `voiceBridge.ts`          | WS connection refused           | Sets status `offline`, shows toast                 | Chat page fully functional; no voice                           |
| `voiceBridge.ts`          | WS drops mid-session            | Auto-reconnects up to 5×                           | Transparent to user if reconnects succeed                      |
| `voiceBridge.ts`          | Max reconnects reached          | Sets status `offline`, shows toast                 | User notified; text chat continues                             |
| `ChatPage.tsx`            | `appendMessage` throws          | Caught in `handleVoiceInteraction`                 | One message may be lost; page doesn't crash                    |
| `auth.py`                 | `VOICE_JWT_SECRET` not set      | Returns HTTP 503 with clear message                | Voice token unavailable; app logs warn                         |

---

> **Summary of install flow:**
> `make install-voice` → `docker compose --profile voice up host-setup` → `detect-host.sh` → `install-voice-bridge.sh` → `register-service.sh` → service starts on host → user opens browser → logs in → `voiceBridgeService.connect()` → voice token issued → bridge activated → say **"Agentium"** → talk to the Head of Council → hear the reply.# Agentium — Host-Native Voice Interface: Complete Implementation

> **Goal:** Detect the host OS at install time, set up a voice bridge process _outside_ Docker, and let the user speak to the Head of Council directly from their desktop after login — with full TTS playback and chat history sync. Every error is caught, logged with a warning, and the rest of the system continues running normally.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Structure](#2-file-structure)
3. [Phase 1 — OS Detection (`scripts/detect-host.sh`)](#3-phase-1--os-detection)
4. [Phase 2 — Dependency Installer (`scripts/install-voice-bridge.sh`)](#4-phase-2--dependency-installer)
5. [Phase 3 — Service Registration (systemd / launchd / WSL2)](#5-phase-3--service-registration)
6. [Phase 4 — Backend Voice Token API](#6-phase-4--backend-voice-token-api)
7. [Phase 5 — Voice Bridge Core (`voice-bridge/main.py`)](#7-phase-5--voice-bridge-core)
8. [Phase 6 — Frontend Integration](#8-phase-6--frontend-integration)
9. [Phase 7 — Docker Compose Wiring](#9-phase-7--docker-compose-wiring)
10. [Error Handling Reference](#10-error-handling-reference)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  HOST OS                                                    │
│                                                             │
│  ┌─────────────────────────────────┐                        │
│  │  voice-bridge/main.py           │  microphone + speakers │
│  │  SecureVoiceBridge              │◄──────────────────────┤│
│  │  • Wake-word detection          │                        │
│  │  • STT  (Vosk offline / Google) │                        │
│  │  • TTS  (pyttsx3)               │                        │
│  │  • WS server  127.0.0.1:9999   │                        │
│  └──────────┬──────────────────────┘                        │
│             │  HTTP  (port 8000)  /  WS events              │
└─────────────┼───────────────────────────────────────────────┘
              │  Docker bridge network
┌─────────────▼───────────────────────────────────────────────┐
│  DOCKER                                                     │
│                                                             │
│  backend (FastAPI :8000)  ←→  Head of Council (LLM)        │
│  frontend (React   :3000)      redis / postgres / chroma    │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** every step that can fail is wrapped in its own error handler. A failed step prints a `[WARN]` or `[ERROR]` banner and either retries, falls back to a safe default, or skips that step — the rest of the installation and the rest of the bridge always continue.

---

## 2. File Structure

```
Agentium/
├── voice-bridge/
│   ├── main.py                  # SecureVoiceBridge — core bridge process
│   ├── requirements.txt         # Pinned Python deps
│   └── install.sh               # Entry-point: calls detect-host.sh then installer
│
├── scripts/
│   ├── detect-host.sh           # Phase 1 — OS probe, writes ~/.agentium/env.conf
│   ├── install-voice-bridge.sh  # Phase 2+3 — venv, deps, service registration
│   └── uninstall-voice-bridge.sh
│
├── backend/
│   ├── api/routes/auth.py       # +POST /auth/voice-token, GET /auth/verify-session
│   └── core/voice_auth.py       # voice-scoped JWT helper
│
├── frontend/src/
│   ├── services/voiceBridge.ts  # Browser WS client
│   ├── hooks/useVoiceBridge.ts  # React hook
│   └── components/
│       └── VoiceIndicator.tsx   # Status badge in MainLayout
│
├── .env.example                 # +VOICE_JWT_SECRET, VOICE_TOKEN_DURATION_MINUTES
├── docker-compose.yml           # +host-setup init service
└── Makefile                     # +install-voice, uninstall-voice, voice-logs
```

---

## 3. Phase 1 — OS Detection

**`scripts/detect-host.sh`**

```bash
#!/usr/bin/env bash
# =============================================================================
# detect-host.sh  — Agentium OS probe
# Writes ~/.agentium/env.conf  (KEY=VALUE pairs consumed by installer + bridge)
# Every check is independent: a failure writes a safe default and warns.
# =============================================================================
set -euo pipefail

CONF_DIR="$HOME/.agentium"
CONF_FILE="$CONF_DIR/env.conf"
LOG_FILE="$CONF_DIR/detect.log"
WARN_COUNT=0

mkdir -p "$CONF_DIR"
: > "$CONF_FILE"          # truncate / create
: > "$LOG_FILE"

# ── helpers ──────────────────────────────────────────────────────────────────

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
conf() { echo "$1=$2" >> "$CONF_FILE"; }       # write a key=value pair
safe_conf() {                                  # write a key=value, warn if value empty
  local key="$1" val="$2" fallback="$3"
  if [[ -z "$val" ]]; then
    warn "Could not detect $key — using fallback: $fallback"
    conf "$key" "$fallback"
  else
    conf "$key" "$val"
  fi
}

log "=== Agentium OS Detection Started ==="

# ── Step 1.1  OS family ───────────────────────────────────────────────────────
log "Step 1.1 — Detecting OS family"
detect_os_family() {
  local uname
  uname=$(uname -s 2>/dev/null) || { warn "uname failed; defaulting to linux"; echo "linux"; return; }
  case "$uname" in
    Darwin)  echo "macos"  ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl2"
      else
        echo "linux"
      fi
      ;;
    MINGW*|CYGWIN*) echo "wsl2" ;;
    *) warn "Unknown OS '$uname'; defaulting to linux"; echo "linux" ;;
  esac
}
OS_FAMILY=$(detect_os_family)
conf "OS_FAMILY" "$OS_FAMILY"
log "  OS_FAMILY=$OS_FAMILY"

# ── Step 1.2  Linux distro ────────────────────────────────────────────────────
log "Step 1.2 — Detecting Linux distro"
DISTRO="unknown"
if [[ "$OS_FAMILY" == "linux" || "$OS_FAMILY" == "wsl2" ]]; then
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release 2>/dev/null || warn "/etc/os-release source failed"
    DISTRO="${ID:-unknown}"
  else
    warn "/etc/os-release not found — distro detection skipped"
  fi
fi
conf "DISTRO" "$DISTRO"
log "  DISTRO=$DISTRO"

# ── Step 1.3  Package manager ─────────────────────────────────────────────────
log "Step 1.3 — Selecting package manager"
detect_pkg_mgr() {
  case "$OS_FAMILY" in
    macos)  command -v brew &>/dev/null && echo "brew" || { warn "Homebrew not found — install from brew.sh first"; echo "brew_missing"; } ;;
    linux|wsl2)
      case "$DISTRO" in
        ubuntu|debian|linuxmint|pop)  echo "apt" ;;
        fedora|rhel|centos|rocky)     echo "dnf" ;;
        arch|manjaro|endeavouros)     echo "pacman" ;;
        opensuse*)                    echo "zypper" ;;
        *)
          # last-resort: probe binaries
          for mgr in apt dnf pacman zypper; do
            command -v "$mgr" &>/dev/null && { echo "$mgr"; return; }
          done
          warn "No known package manager found; manual install required"
          echo "unknown"
          ;;
      esac
      ;;
    *) warn "Cannot determine package manager for OS_FAMILY=$OS_FAMILY"; echo "unknown" ;;
  esac
}
PKG_MGR=$(detect_pkg_mgr)
conf "PKG_MGR" "$PKG_MGR"
log "  PKG_MGR=$PKG_MGR"

# ── Step 1.4  Python version ──────────────────────────────────────────────────
log "Step 1.4 — Checking Python ≥ 3.10"
detect_python() {
  for bin in python3.12 python3.11 python3.10 python3; do
    if command -v "$bin" &>/dev/null; then
      local ver
      ver=$("$bin" -c "import sys; print(sys.version_info[:2])" 2>/dev/null) || continue
      # ver looks like "(3, 11)"
      local major minor
      major=$(echo "$ver" | tr -d '(),' | awk '{print $1}')
      minor=$(echo "$ver" | tr -d '(),' | awk '{print $2}')
      if (( major >= 3 && minor >= 10 )); then
        echo "$bin"
        return
      fi
    fi
  done
  warn "No Python ≥ 3.10 found. Bridge STT/TTS will not function. Install Python 3.10+ and re-run."
  echo "python3_missing"
}
PYTHON_BIN=$(detect_python)
conf "PYTHON_BIN" "$PYTHON_BIN"
log "  PYTHON_BIN=$PYTHON_BIN"

# ── Step 1.5  PortAudio ───────────────────────────────────────────────────────
log "Step 1.5 — Checking PortAudio"
PORTAUDIO_INSTALLED="false"
check_portaudio() {
  case "$OS_FAMILY" in
    macos)  [[ -d /opt/homebrew/include/portaudio* ]] || [[ -d /usr/local/include/portaudio* ]] && echo "true" || echo "false" ;;
    *)
      pkg-config --exists portaudio-2.0 2>/dev/null && echo "true" || echo "false"
      ;;
  esac
}
PORTAUDIO_INSTALLED=$(check_portaudio 2>/dev/null || echo "false")
if [[ "$PORTAUDIO_INSTALLED" == "false" ]]; then
  warn "PortAudio not found — installer will attempt to install it"
fi
conf "PORTAUDIO_INSTALLED" "$PORTAUDIO_INSTALLED"
log "  PORTAUDIO_INSTALLED=$PORTAUDIO_INSTALLED"

# ── Step 1.6  Service manager ─────────────────────────────────────────────────
log "Step 1.6 — Detecting service manager"
detect_svc_mgr() {
  case "$OS_FAMILY" in
    macos)  command -v launchctl &>/dev/null && echo "launchd" || { warn "launchctl missing"; echo "manual"; } ;;
    linux)  systemctl --user status &>/dev/null 2>&1 && echo "systemd" || { warn "systemd --user not available; will use manual startup"; echo "manual"; } ;;
    wsl2)   echo "wsl2" ;;
    *)      warn "Unknown OS for service manager"; echo "manual" ;;
  esac
}
SVC_MGR=$(detect_svc_mgr)
conf "SVC_MGR" "$SVC_MGR"
log "  SVC_MGR=$SVC_MGR"

# ── Step 1.7  Docker gateway IP ───────────────────────────────────────────────
log "Step 1.7 — Probing Docker gateway IP"
detect_backend_host() {
  # Try host.docker.internal first (Docker Desktop / newer Linux)
  if ping -c1 -W1 host.docker.internal &>/dev/null 2>&1; then
    echo "host.docker.internal"
    return
  fi
  # Try docker0 interface
  local ip
  ip=$(ip route 2>/dev/null | awk '/docker0/ {print $9; exit}')
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  # Try default gateway on docker0 subnet
  ip=$(ip addr show docker0 2>/dev/null | awk '/inet / {split($2,a,"/"); print a[1]}')
  [[ -n "$ip" ]] && { echo "$ip"; return; }
  warn "Cannot auto-detect Docker gateway. Defaulting to 172.17.0.1 — edit ~/.agentium/env.conf if wrong."
  echo "172.17.0.1"
}
BACKEND_HOST=$(detect_backend_host)
conf "BACKEND_HOST" "$BACKEND_HOST"
conf "BACKEND_PORT" "8000"
conf "BRIDGE_WS_PORT" "9999"
log "  BACKEND_HOST=$BACKEND_HOST"

# ── Step 1.8  Microphone check ────────────────────────────────────────────────
log "Step 1.8 — Checking for microphone"
HAS_MIC="false"
check_mic() {
  case "$OS_FAMILY" in
    macos)
      system_profiler SPAudioDataType 2>/dev/null | grep -qi "microphone" && echo "true" || echo "false"
      ;;
    linux|wsl2)
      # arecord -l lists capture devices; non-zero exit means none
      if command -v arecord &>/dev/null; then
        arecord -l 2>/dev/null | grep -q "card" && echo "true" || echo "false"
      else
        # fall back to /proc/asound
        ls /proc/asound/card*/pcm*c 2>/dev/null | head -1 | grep -q pcm && echo "true" || echo "false"
      fi
      ;;
    *) echo "unknown" ;;
  esac
}
HAS_MIC=$(check_mic 2>/dev/null || echo "unknown")
if [[ "$HAS_MIC" == "false" ]]; then
  warn "No microphone detected. Voice capture will fail at runtime — connect a mic and restart the bridge."
fi
conf "HAS_MIC" "$HAS_MIC"
conf "VENV_PATH" "$HOME/.agentium-voice"
log "  HAS_MIC=$HAS_MIC"

# ── Summary ───────────────────────────────────────────────────────────────────
log "=== Detection complete. $WARN_COUNT warning(s). Config written to $CONF_FILE ==="
if (( WARN_COUNT > 0 )); then
  echo ""
  echo "⚠  $WARN_COUNT warning(s) during detection. Review $LOG_FILE for details."
  echo "   Non-critical warnings are safe to ignore; the installer will handle them."
  echo ""
fi
cat "$CONF_FILE"
```

---

## 4. Phase 2 — Dependency Installer

**`scripts/install-voice-bridge.sh`**

```bash
#!/usr/bin/env bash
# =============================================================================
# install-voice-bridge.sh  — Agentium Voice Bridge Installer
# Reads ~/.agentium/env.conf  produced by detect-host.sh
# Every step has its own error handler — a failure warns and continues.
# =============================================================================
set -uo pipefail     # -e intentionally OFF: we handle errors per-step

CONF_FILE="$HOME/.agentium/env.conf"
LOG_FILE="$HOME/.agentium/install.log"
WARN_COUNT=0
FAIL_COUNT=0

# ── helpers ──────────────────────────────────────────────────────────────────
log()   { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn()  { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
fail()  { echo "[ERROR] $*" | tee -a "$LOG_FILE" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }
ok()    { echo "[OK]    $*" | tee -a "$LOG_FILE"; }
step()  { echo "" | tee -a "$LOG_FILE"; echo "──── $* ────" | tee -a "$LOG_FILE"; }

# run a command; on non-zero exit: warn and return 1 (caller decides whether fatal)
run_or_warn() {
  local label="$1"; shift
  if "$@" >> "$LOG_FILE" 2>&1; then
    ok "$label"
    return 0
  else
    warn "$label failed (exit $?). See $LOG_FILE for details. Continuing."
    return 1
  fi
}

# ── Load config ───────────────────────────────────────────────────────────────
if [[ ! -f "$CONF_FILE" ]]; then
  echo "[ERROR] $CONF_FILE not found. Run scripts/detect-host.sh first."
  exit 1
fi
# shellcheck disable=SC1090
source "$CONF_FILE"
: > "$LOG_FILE"
log "=== Agentium Voice Bridge Installer ==="
log "Loaded config from $CONF_FILE"

VENV="${VENV_PATH:-$HOME/.agentium-voice}"
PYTHON="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_DIR="$(dirname "$SCRIPT_DIR")/voice-bridge"

# ── Step 2.1  System packages ─────────────────────────────────────────────────
step "2.1  Installing system packages"
install_system_packages() {
  case "${PKG_MGR:-unknown}" in
    apt)
      run_or_warn "apt update" sudo apt-get update -qq || true
      run_or_warn "apt install audio libs" \
        sudo apt-get install -y -qq python3-dev portaudio19-dev libespeak-ng1 ffmpeg alsa-utils
      ;;
    dnf)
      run_or_warn "dnf install audio libs" \
        sudo dnf install -y -q python3-devel portaudio-devel espeak-ng ffmpeg
      ;;
    pacman)
      run_or_warn "pacman install audio libs" \
        sudo pacman -S --noconfirm --needed python portaudio espeak-ng ffmpeg
      ;;
    brew)
      run_or_warn "brew install portaudio" brew install portaudio
      ;;
    brew_missing)
      warn "Homebrew not installed. Visit https://brew.sh — then re-run this script."
      ;;
    unknown|*)
      warn "Unknown package manager '${PKG_MGR:-}'. Skipping system package install."
      warn "Manually install: portaudio-dev, espeak-ng, ffmpeg, python3-dev"
      ;;
  esac
}
install_system_packages

# ── Step 2.2  Python venv ─────────────────────────────────────────────────────
step "2.2  Creating Python venv at $VENV"
if [[ "${PYTHON_BIN:-python3_missing}" == "python3_missing" ]]; then
  warn "Python ≥ 3.10 not found — skipping venv creation. Bridge will not function."
else
  if [[ -d "$VENV" ]]; then
    log "  Existing venv found at $VENV — upgrading in place (idempotent)"
  else
    run_or_warn "Create venv" "$PYTHON" -m venv "$VENV" || {
      fail "Could not create venv at $VENV. Bridge will not function."
    }
  fi
fi

# ── Step 2.3  pip install ─────────────────────────────────────────────────────
step "2.3  Installing Python packages"
REQUIREMENTS="$BRIDGE_DIR/requirements.txt"
if [[ ! -f "$REQUIREMENTS" ]]; then
  warn "requirements.txt not found at $REQUIREMENTS — writing defaults"
  mkdir -p "$BRIDGE_DIR"
  cat > "$REQUIREMENTS" <<EOF
websockets>=12.0
SpeechRecognition>=3.10
pyttsx3>=2.90
PyAudio>=0.2.14
vosk>=0.3.45
requests>=2.31
PyJWT>=2.8
EOF
fi

if [[ -x "$VENV/bin/pip" ]]; then
  run_or_warn "pip upgrade" "$VENV/bin/pip" install --quiet --upgrade pip
  # Install each package individually so one failure doesn't abort the rest
  while IFS= read -r pkg || [[ -n "$pkg" ]]; do
    [[ -z "$pkg" || "$pkg" == \#* ]] && continue
    if run_or_warn "pip install $pkg" "$VENV/bin/pip" install --quiet "$pkg"; then
      ok "  Installed: $pkg"
    else
      warn "  Could not install $pkg — some voice features may be degraded."
    fi
  done < "$REQUIREMENTS"
else
  warn "pip not found in venv. Skipping Python package install."
fi

# ── Step 2.4  Copy bridge source ──────────────────────────────────────────────
step "2.4  Copying bridge source to venv"
if [[ -f "$BRIDGE_DIR/main.py" ]]; then
  cp "$BRIDGE_DIR/main.py" "$VENV/main.py" && ok "main.py copied" || warn "Could not copy main.py — service will use source path instead"
fi

# ── Step 2.5  Write env.conf additions ───────────────────────────────────────
step "2.5  Finalising env.conf"
{
  echo "VENV_PATH=$VENV"
  echo "BRIDGE_MAIN=$VENV/main.py"
  echo "INSTALL_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$CONF_FILE"
ok "env.conf updated"

# ── Step 2.6  Summary ─────────────────────────────────────────────────────────
echo ""
if (( FAIL_COUNT > 0 )); then
  echo "⛔  Install finished with $FAIL_COUNT fatal error(s) and $WARN_COUNT warning(s)."
  echo "   Voice bridge may not function correctly. Review $LOG_FILE"
elif (( WARN_COUNT > 0 )); then
  echo "⚠   Install finished with $WARN_COUNT warning(s) — non-critical, continuing."
  echo "   Review $LOG_FILE for details."
else
  echo "✅  Install complete — no warnings."
fi

# Always continue to service registration regardless of warnings
bash "$(dirname "${BASH_SOURCE[0]}")/register-service.sh"
```

**`voice-bridge/requirements.txt`**

```
websockets>=12.0
SpeechRecognition>=3.10
pyttsx3>=2.90
PyAudio>=0.2.14
vosk>=0.3.45
requests>=2.31
PyJWT>=2.8
```

---

## 5. Phase 3 — Service Registration

**`scripts/register-service.sh`** (called at the end of the installer)

```bash
#!/usr/bin/env bash
# =============================================================================
# register-service.sh  — Registers agentium-voice as a background service
# Reads SVC_MGR from env.conf and branches to the correct method.
# Failures warn but never abort — bridge can always be started manually.
# =============================================================================
set -uo pipefail

CONF_FILE="$HOME/.agentium/env.conf"
LOG_FILE="$HOME/.agentium/install.log"
WARN_COUNT=0

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
ok()   { echo "[OK]    $*" | tee -a "$LOG_FILE"; }

# shellcheck disable=SC1090
source "$CONF_FILE" 2>/dev/null || { warn "Could not source $CONF_FILE"; }

VENV="${VENV_PATH:-$HOME/.agentium-voice}"
BRIDGE_MAIN="${BRIDGE_MAIN:-$VENV/main.py}"
PYTHON_EXE="$VENV/bin/python"

# ── 3a  systemd ───────────────────────────────────────────────────────────────
register_systemd() {
  local unit_dir="$HOME/.config/systemd/user"
  local unit_file="$unit_dir/agentium-voice.service"
  mkdir -p "$unit_dir"

  cat > "$unit_file" <<EOF
[Unit]
Description=Agentium Voice Bridge
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$PYTHON_EXE $BRIDGE_MAIN
Restart=on-failure
RestartSec=5
EnvironmentFile=$HOME/.agentium/env.conf

[Install]
WantedBy=default.target
EOF

  if systemctl --user daemon-reload 2>/dev/null; then
    ok "systemd daemon-reload"
  else
    warn "daemon-reload failed — run manually: systemctl --user daemon-reload"
  fi

  if systemctl --user enable --now agentium-voice 2>/dev/null; then
    ok "agentium-voice enabled and started"
  else
    warn "Could not enable/start agentium-voice — start manually:"
    warn "  systemctl --user start agentium-voice"
  fi
}

# ── 3b  launchd ───────────────────────────────────────────────────────────────
register_launchd() {
  local plist_dir="$HOME/Library/LaunchAgents"
  local plist_file="$plist_dir/com.agentium.voice.plist"
  mkdir -p "$plist_dir"

  # Unload existing if present (idempotent upgrade)
  if [[ -f "$plist_file" ]]; then
    launchctl unload "$plist_file" 2>/dev/null || true
    ok "Unloaded existing launchd job (upgrading)"
  fi

  cat > "$plist_file" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.agentium.voice</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_EXE</string>
    <string>$BRIDGE_MAIN</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>StandardOutPath</key>
  <string>$HOME/.agentium/voice-bridge.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.agentium/voice-bridge.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>VENV_PATH</key>       <string>$VENV</string>
    <key>BACKEND_HOST</key>    <string>${BACKEND_HOST:-172.17.0.1}</string>
    <key>BACKEND_PORT</key>    <string>${BACKEND_PORT:-8000}</string>
    <key>BRIDGE_WS_PORT</key>  <string>${BRIDGE_WS_PORT:-9999}</string>
  </dict>
</dict>
</plist>
EOF

  if launchctl load "$plist_file" 2>/dev/null; then
    ok "launchd job loaded: com.agentium.voice"
  else
    warn "launchctl load failed. Try: launchctl load $plist_file"
  fi
}

# ── 3c  WSL2 shim ─────────────────────────────────────────────────────────────
register_wsl2() {
  local startup_script="$HOME/.agentium/start-voice.sh"

  cat > "$startup_script" <<EOF
#!/usr/bin/env bash
# WSL2 Voice Bridge Startup — sourced by Windows Task Scheduler
source "$HOME/.agentium/env.conf" 2>/dev/null || true
exec "$PYTHON_EXE" "$BRIDGE_MAIN" >> "$HOME/.agentium/voice-bridge.log" 2>&1
EOF
  chmod +x "$startup_script"
  ok "WSL2 startup script written: $startup_script"

  # Attempt to register a Windows scheduled task via powershell.exe
  local task_cmd
  task_cmd='schtasks /Create /F /TN "AgentiumVoiceBridge" /TR "wsl.exe -e bash '"$startup_script"'" /SC ONLOGON /RL LIMITED'
  if command -v powershell.exe &>/dev/null; then
    if powershell.exe -Command "$task_cmd" >> "$LOG_FILE" 2>&1; then
      ok "Windows Task Scheduler entry created"
    else
      warn "Could not create scheduled task automatically."
      warn "Run in PowerShell (as user): $task_cmd"
    fi
  else
    warn "powershell.exe not accessible from WSL2. Register the task manually:"
    warn "  $task_cmd"
  fi

  echo ""
  echo "  ℹ  WSL2 audio note: ensure WSLg or PulseAudio bridge is active."
  echo "     Check: pactl list sources | grep -i micro"
}

# ── 3d  Manual fallback ───────────────────────────────────────────────────────
register_manual() {
  warn "No supported service manager found (SVC_MGR=${SVC_MGR:-unknown})"
  warn "Start the bridge manually with:"
  warn "  $PYTHON_EXE $BRIDGE_MAIN"
  local rc_file=""
  [[ -f "$HOME/.zshrc" ]]  && rc_file="$HOME/.zshrc"
  [[ -f "$HOME/.bashrc" ]] && rc_file="$HOME/.bashrc"
  if [[ -n "$rc_file" ]]; then
    warn "Or add to $rc_file:"
    warn "  nohup $PYTHON_EXE $BRIDGE_MAIN &>/dev/null &"
  fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
log "=== Service Registration (SVC_MGR=${SVC_MGR:-unknown}) ==="
case "${SVC_MGR:-unknown}" in
  systemd) register_systemd ;;
  launchd) register_launchd ;;
  wsl2)    register_wsl2    ;;
  *)       register_manual  ;;
esac

if (( WARN_COUNT > 0 )); then
  echo "⚠  $WARN_COUNT service-registration warning(s). Review $LOG_FILE"
else
  echo "✅  Service registered successfully."
fi
echo "   To start manually: $PYTHON_EXE $BRIDGE_MAIN"
```

---

## 6. Phase 4 — Backend Voice Token API

**`backend/core/voice_auth.py`**

```python
"""
voice_auth.py — Helper for creating and verifying voice-scoped JWTs.
All errors are caught and re-raised as HTTPException so FastAPI
returns clean 401/500 responses rather than unhandled 500s.
"""
import os
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger("agentium.voice_auth")

VOICE_SECRET   = os.getenv("VOICE_JWT_SECRET", "")
DURATION_MIN   = int(os.getenv("VOICE_TOKEN_DURATION_MINUTES", "30"))
ALGORITHM      = "HS256"


def _require_secret() -> str:
    """Return the voice JWT secret or raise a clear 500 with a log warning."""
    if not VOICE_SECRET:
        logger.warning(
            "VOICE_JWT_SECRET is not set in environment. "
            "Voice token issuance is disabled. Set the variable and restart."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice token service not configured. Contact your administrator.",
        )
    return VOICE_SECRET


def create_voice_token(user_id: str) -> tuple[str, datetime]:
    """
    Issue a short-lived voice-scoped JWT.
    Returns (token_string, expiry_datetime).
    Raises HTTPException on misconfiguration.
    """
    secret = _require_secret()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=DURATION_MIN)
    payload = {
        "sub":   user_id,
        "scope": "voice_command",
        "exp":   expires_at,
        "iat":   datetime.now(timezone.utc),
    }
    try:
        token = jwt.encode(payload, secret, algorithm=ALGORITHM)
        return token, expires_at
    except Exception as exc:
        logger.error("Failed to encode voice token: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not issue voice token.",
        ) from exc


def verify_voice_token(token: str) -> dict:
    """
    Decode and validate a voice-scoped JWT.
    Returns the payload dict.
    Raises HTTPException on any validation failure.
    """
    secret = _require_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Voice token has expired.")
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid voice token received: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid voice token.")
    if payload.get("scope") != "voice_command":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Token scope is not 'voice_command'.")
    return payload
```

**Additions to `backend/api/routes/auth.py`**

```python
# ── append to existing auth.py ────────────────────────────────────────────────
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from backend.core.voice_auth import create_voice_token
from backend.api.dependencies.auth import get_current_user  # existing dep

import logging
logger = logging.getLogger("agentium.routes.auth")


class VoiceTokenResponse(BaseModel):
    voice_token: str
    expires_at:  datetime


class SessionVerifyResponse(BaseModel):
    user_id:    str
    expires_at: datetime


@router.post("/voice-token", response_model=VoiceTokenResponse)
async def issue_voice_token(current_user=Depends(get_current_user)):
    """
    Issue a 30-minute voice-scoped JWT.
    Called by the browser immediately after login to activate the host bridge.
    """
    try:
        token, expires_at = create_voice_token(str(current_user.id))
        return VoiceTokenResponse(voice_token=token, expires_at=expires_at)
    except HTTPException:
        raise   # already formatted
    except Exception as exc:
        logger.error("Unexpected error in /voice-token: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Voice token error.")


@router.get("/verify-session", response_model=SessionVerifyResponse)
async def verify_session(current_user=Depends(get_current_user)):
    """
    Called by the voice bridge to confirm the browser session is still live.
    Uses the same auth dependency as all other protected routes.
    """
    try:
        return SessionVerifyResponse(
            user_id=str(current_user.id),
            expires_at=current_user.token_expires,   # set by your existing auth middleware
        )
    except AttributeError:
        # token_expires may not exist on all user objects
        logger.warning("verify-session: current_user missing token_expires")
        from datetime import timezone, timedelta
        return SessionVerifyResponse(
            user_id=str(current_user.id),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
```

**.env.example additions**

```env
# ── Voice Bridge ──────────────────────────────────────────────────────────────
VOICE_JWT_SECRET=change-me-to-a-random-32-char-string
VOICE_TOKEN_DURATION_MINUTES=30
```

---

## 7. Phase 5 — Voice Bridge Core

**`voice-bridge/main.py`**

```python
"""
main.py  —  Agentium Host-Native Voice Bridge
SecureVoiceBridge:
  • Runs a WebSocket server on 127.0.0.1:9999 (browser auth gate)
  • Waits idle until the browser sends a valid auth_delegate message
  • Enters wake-word → STT → POST /chat → TTS loop
  • Syncs every exchange back to the browser (ChatPage updates)
  • Every sub-system failure is caught, logged, and continues gracefully
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import jwt
import requests
import websockets
from websockets.server import WebSocketServerProtocol

# ── optional audio imports — warn if missing, bridge still starts ─────────────
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.warning("[WARN] SpeechRecognition not installed — STT unavailable. "
                    "Install: pip install SpeechRecognition PyAudio")

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("[WARN] pyttsx3 not installed — TTS (speaker playback) unavailable. "
                    "Install: pip install pyttsx3")

try:
    import vosk  # noqa: F401 — checked at model-load time below
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logging.info("[INFO] vosk not installed — offline STT fallback unavailable.")


# ── logging setup ─────────────────────────────────────────────────────────────
LOG_FILE = os.path.expanduser("~/.agentium/voice-bridge.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agentium.voice")

# ── config from env.conf (loaded as env vars by service manager) ──────────────
BACKEND_HOST   = os.getenv("BACKEND_HOST",   "172.17.0.1")
BACKEND_PORT   = os.getenv("BACKEND_PORT",   "8000")
BRIDGE_PORT    = int(os.getenv("BRIDGE_WS_PORT", "9999"))
VOICE_SECRET   = os.getenv("VOICE_JWT_SECRET", "")
BACKEND_URL    = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
WAKE_WORDS     = {"agentium", "hey agentium"}

# ── TTS engine (singleton, initialised once) ──────────────────────────────────
_tts_engine: Optional["pyttsx3.Engine"] = None
_tts_lock = threading.Lock()

def _get_tts() -> Optional["pyttsx3.Engine"]:
    global _tts_engine
    if not TTS_AVAILABLE:
        return None
    if _tts_engine is None:
        with _tts_lock:
            if _tts_engine is None:
                try:
                    _tts_engine = pyttsx3.init()
                    _tts_engine.setProperty("rate", 165)
                    log.info("TTS engine initialised")
                except Exception as exc:
                    log.warning("[WARN] Could not initialise TTS engine: %s — "
                                "replies will not be spoken aloud.", exc)
    return _tts_engine


def speak(text: str) -> None:
    """Speak text via host TTS. Silently skipped if engine unavailable."""
    engine = _get_tts()
    if engine is None:
        log.info("[TTS-SKIP] %s", text)
        return
    try:
        with _tts_lock:
            engine.say(text)
            engine.runAndWait()
    except Exception as exc:
        log.warning("[WARN] TTS playback failed: %s — continuing without audio.", exc)


# ── STT ───────────────────────────────────────────────────────────────────────
def transcribe_audio(timeout: int = 5, phrase_limit: int = 15) -> Optional[str]:
    """
    Capture one phrase from the microphone and return the transcription.
    Returns None on any error (caller decides what to do).
    Tries Google STT first; falls back to Vosk offline if network fails.
    """
    if not SR_AVAILABLE:
        log.warning("[WARN] SpeechRecognition unavailable — cannot capture audio.")
        return None

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            log.info("STT: listening (timeout=%ds, phrase_limit=%ds)…", timeout, phrase_limit)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
    except sr.WaitTimeoutError:
        log.info("STT: listen timed out — no speech detected.")
        return None
    except OSError as exc:
        log.warning("[WARN] Microphone error: %s — check mic connection.", exc)
        return None
    except Exception as exc:
        log.warning("[WARN] Unexpected STT capture error: %s", exc)
        return None

    # ── Try Google STT ────────────────────────────────────────────────────────
    try:
        text = recognizer.recognize_google(audio)
        log.info("STT (Google): %r", text)
        return text.strip()
    except sr.UnknownValueError:
        log.info("STT: speech not understood")
        return None
    except sr.RequestError as exc:
        log.warning("[WARN] Google STT unavailable: %s — trying offline Vosk.", exc)

    # ── Vosk offline fallback ─────────────────────────────────────────────────
    if VOSK_AVAILABLE:
        try:
            import vosk as vosk_mod
            model_path = os.path.expanduser("~/.agentium/vosk-model")
            if not os.path.isdir(model_path):
                log.warning("[WARN] Vosk model not found at %s. "
                            "Download from https://alphacephei.com/vosk/models", model_path)
                return None
            model = vosk_mod.Model(model_path)
            rec = vosk_mod.KaldiRecognizer(model, 16000)
            raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
            rec.AcceptWaveform(raw)
            result = json.loads(rec.Result())
            text = result.get("text", "").strip()
            log.info("STT (Vosk offline): %r", text)
            return text or None
        except Exception as exc:
            log.warning("[WARN] Vosk offline STT failed: %s", exc)

    return None


# ── Backend communication ─────────────────────────────────────────────────────
def post_to_chat(transcription: str, voice_token: str) -> Optional[str]:
    """
    POST transcription to /api/chat using the voice-scoped token.
    Returns the agent reply text, or None on any error.
    """
    url = f"{BACKEND_URL}/api/chat"
    headers = {
        "Authorization": f"Bearer {voice_token}",
        "Content-Type":  "application/json",
    }
    payload = {
        "message": transcription,
        "source":  "voice",
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        # Support multiple response shapes gracefully
        reply = (
            data.get("reply")
            or data.get("response")
            or data.get("message")
            or data.get("content")
            or str(data)
        )
        log.info("Chat response received (%d chars)", len(reply))
        return reply
    except requests.exceptions.ConnectionError:
        log.warning("[WARN] Cannot reach backend at %s — is Docker running?", BACKEND_URL)
    except requests.exceptions.Timeout:
        log.warning("[WARN] Backend request timed out after 30s.")
    except requests.exceptions.HTTPError as exc:
        log.warning("[WARN] Backend returned HTTP %s: %s", exc.response.status_code, exc)
    except Exception as exc:
        log.warning("[WARN] Unexpected error calling chat API: %s", exc)
    return None


def verify_session_with_backend(browser_jwt: str) -> bool:
    """
    Ask the backend to validate the browser's JWT.
    Returns True on 200, False on any error.
    """
    url = f"{BACKEND_URL}/api/auth/verify-session"
    headers = {"Authorization": f"Bearer {browser_jwt}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            log.info("Session verified with backend.")
            return True
        log.warning("[WARN] verify-session returned %d — rejecting bridge activation.",
                    response.status_code)
        return False
    except requests.exceptions.ConnectionError:
        log.warning("[WARN] Backend unreachable during verify-session. "
                    "Activating bridge in offline mode (reduced security).")
        return True   # degraded but continue — allows offline dev use
    except Exception as exc:
        log.warning("[WARN] verify-session error: %s — activating in offline mode.", exc)
        return True


# ── Main bridge class ─────────────────────────────────────────────────────────
class SecureVoiceBridge:
    """
    State machine:
      IDLE → (browser connects + auth) → WAITING_FOR_WAKE_WORD
           → (wake-word) → CAPTURING_COMMAND
           → (speech) → PROCESSING
           → (reply) → SPEAKING → WAITING_FOR_WAKE_WORD
           → (browser disconnects or token expires) → IDLE
    """

    IDLE                  = "idle"
    WAITING_FOR_WAKE_WORD = "waiting_for_wake_word"
    CAPTURING_COMMAND     = "capturing_command"
    PROCESSING            = "processing"
    SPEAKING              = "speaking"
    EXPIRED               = "expired"

    def __init__(self) -> None:
        self.state:        str                         = self.IDLE
        self.voice_token:  Optional[str]               = None
        self.browser_jwt:  Optional[str]               = None
        self.token_expires: Optional[datetime]         = None
        self._browser_ws:  Optional[WebSocketServerProtocol] = None
        self._stop_event   = asyncio.Event()
        self._listen_task: Optional[asyncio.Task]      = None

    # ── Token helpers ─────────────────────────────────────────────────────────

    def _token_valid(self) -> bool:
        if not self.voice_token or not self.token_expires:
            return False
        if datetime.now(timezone.utc) >= self.token_expires:
            log.info("Voice token has expired.")
            return False
        return True

    def _parse_expiry(self, expires_at: str) -> Optional[datetime]:
        """Parse ISO8601 string from the browser's auth_delegate message."""
        try:
            # Handle both Z and +00:00 suffixes
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return dt
        except (ValueError, AttributeError) as exc:
            log.warning("[WARN] Could not parse token expiry %r: %s — "
                        "defaulting to 30 minutes from now.", expires_at, exc)
            from datetime import timedelta
            return datetime.now(timezone.utc) + timedelta(minutes=30)

    # ── WebSocket server ──────────────────────────────────────────────────────

    async def handle_browser_ws(self, websocket: WebSocketServerProtocol) -> None:
        """Handle a single browser WebSocket connection."""
        log.info("Browser connected from %s", websocket.remote_address)
        self._browser_ws = websocket

        try:
            async for raw_message in websocket:
                await self._process_browser_message(raw_message)
        except websockets.exceptions.ConnectionClosedOK:
            log.info("Browser WebSocket closed cleanly.")
        except websockets.exceptions.ConnectionClosedError as exc:
            log.warning("[WARN] Browser WebSocket closed with error: %s", exc)
        except Exception as exc:
            log.warning("[WARN] Unexpected browser WS error: %s", exc)
        finally:
            await self._on_browser_disconnect()

    async def _process_browser_message(self, raw: str) -> None:
        """Parse and dispatch a message from the browser."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("[WARN] Invalid JSON from browser: %s — ignoring.", exc)
            return

        msg_type = msg.get("type", "")

        if msg_type == "auth_delegate":
            await self._handle_auth_delegate(msg)
        elif msg_type == "logout":
            log.info("Browser sent logout — deactivating bridge.")
            await self._on_browser_disconnect()
        elif msg_type == "ping":
            await self._send_to_browser({"type": "pong"})
        else:
            log.info("Unknown browser message type %r — ignoring.", msg_type)

    async def _handle_auth_delegate(self, msg: dict) -> None:
        """Validate auth_delegate and activate listening if credentials are good."""
        browser_jwt  = msg.get("browserJwt",  "")
        voice_token  = msg.get("voiceToken",  "")
        expires_at   = msg.get("expiresAt",   "")

        if not browser_jwt or not voice_token:
            log.warning("[WARN] auth_delegate missing fields — ignoring.")
            await self._send_to_browser({
                "type": "auth_error",
                "detail": "Missing browserJwt or voiceToken in auth_delegate.",
            })
            return

        # Verify the browser's session JWT with the backend (non-blocking)
        session_ok = await asyncio.get_event_loop().run_in_executor(
            None, verify_session_with_backend, browser_jwt
        )
        if not session_ok:
            log.warning("[WARN] Backend rejected browser session — bridge stays idle.")
            await self._send_to_browser({
                "type": "auth_error",
                "detail": "Session verification failed. Please log in again.",
            })
            return

        # Locally decode voice token for expiry (no network call needed)
        if VOICE_SECRET:
            try:
                jwt.decode(voice_token, VOICE_SECRET, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                log.warning("[WARN] Voice token already expired — rejecting.")
                await self._send_to_browser({"type": "auth_error", "detail": "Voice token expired."})
                return
            except jwt.InvalidTokenError as exc:
                log.warning("[WARN] Voice token invalid: %s", exc)
                # Don't hard-reject — backend will catch invalid tokens on /chat calls
        else:
            log.warning("[WARN] VOICE_JWT_SECRET not set — skipping local token validation.")

        self.browser_jwt   = browser_jwt
        self.voice_token   = voice_token
        self.token_expires = self._parse_expiry(expires_at)
        self.state         = self.WAITING_FOR_WAKE_WORD

        log.info("Bridge activated. Listening for wake-word %r.", WAKE_WORDS)
        await self._send_to_browser({"type": "bridge_activated", "state": self.state})

        # Start the listen loop if not already running
        if self._listen_task is None or self._listen_task.done():
            self._listen_task = asyncio.create_task(self._listen_loop())

    async def _on_browser_disconnect(self) -> None:
        """Clear all auth state when the browser disconnects."""
        self.state         = self.IDLE
        self.voice_token   = None
        self.browser_jwt   = None
        self.token_expires = None
        self._browser_ws   = None
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        log.info("Bridge deactivated — back to idle.")

    async def _send_to_browser(self, payload: dict) -> None:
        """Send a JSON message to the browser. Silently skip if not connected."""
        if self._browser_ws is None:
            return
        try:
            await self._browser_ws.send(json.dumps(payload))
        except Exception as exc:
            log.warning("[WARN] Could not send message to browser: %s", exc)

    # ── Listen loop ───────────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """
        Main voice exchange loop. Runs in the background.
        Checks token validity before each action.
        Falls back gracefully on every possible failure.
        """
        log.info("Listen loop started.")
        while self.state != self.IDLE:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                log.info("Listen loop cancelled.")
                break
            except Exception as exc:
                log.warning("[WARN] Unexpected error in listen loop: %s — retrying in 2s.", exc)
                await asyncio.sleep(2)
        log.info("Listen loop exited.")

    async def _listen_once(self) -> None:
        """Execute one full wake-word → command → reply cycle."""
        # ── Token expiry check ────────────────────────────────────────────────
        if not self._token_valid():
            self.state = self.EXPIRED
            log.info("Token expired — notifying browser and going idle.")
            await self._send_to_browser({"type": "token_expired"})
            speak("Your session has expired. Please log in again to continue.")
            await self._on_browser_disconnect()
            return

        # ── Yield control so the WS server can run ────────────────────────────
        await asyncio.sleep(0.1)

        # ── Wake-word detection ───────────────────────────────────────────────
        if self.state != self.WAITING_FOR_WAKE_WORD:
            return

        transcription = await asyncio.get_event_loop().run_in_executor(
            None, transcribe_audio, 3, 4   # short timeout for wake-word polling
        )
        if transcription is None:
            return   # nothing heard, loop again

        if not any(w in transcription.lower() for w in WAKE_WORDS):
            log.info("STT heard %r but no wake-word — ignoring.", transcription)
            return

        # ── Command capture ───────────────────────────────────────────────────
        self.state = self.CAPTURING_COMMAND
        await self._send_to_browser({"type": "state_change", "state": self.state})
        speak("Yes, I'm listening.")

        command = await asyncio.get_event_loop().run_in_executor(
            None, transcribe_audio, 5, 15
        )
        if not command:
            log.info("No command heard after wake-word — returning to standby.")
            speak("I didn't catch that. Say 'Agentium' again when ready.")
            self.state = self.WAITING_FOR_WAKE_WORD
            await self._send_to_browser({"type": "state_change", "state": self.state})
            return

        log.info("Command captured: %r", command)
        await self._send_to_browser({"type": "transcription", "text": command})

        # ── Processing ────────────────────────────────────────────────────────
        self.state = self.PROCESSING
        await self._send_to_browser({"type": "state_change", "state": self.state})

        reply = await asyncio.get_event_loop().run_in_executor(
            None, post_to_chat, command, self.voice_token
        )
        if reply is None:
            log.warning("[WARN] No reply from backend — telling user and returning to standby.")
            speak("I'm having trouble reaching the backend right now. Please try again.")
            self.state = self.WAITING_FOR_WAKE_WORD
            await self._send_to_browser({"type": "state_change", "state": self.state})
            return

        # ── Speaking ──────────────────────────────────────────────────────────
        self.state = self.SPEAKING
        await self._send_to_browser({
            "type":   "voice_interaction",
            "user":   command,
            "reply":  reply,
        })
        speak(reply)

        self.state = self.WAITING_FOR_WAKE_WORD
        await self._send_to_browser({"type": "state_change", "state": self.state})

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the WebSocket server and run until stopped."""
        log.info("Starting voice bridge WS server on 127.0.0.1:%d", BRIDGE_PORT)
        try:
            async with websockets.serve(
                self.handle_browser_ws,
                "127.0.0.1",
                BRIDGE_PORT,
                ping_interval=20,
                ping_timeout=10,
            ):
                log.info("Voice bridge ready. Waiting for browser connection…")
                await asyncio.Future()   # run forever
        except OSError as exc:
            log.error("[ERROR] Cannot bind to port %d: %s", BRIDGE_PORT, exc)
            log.error("        Is another instance already running? "
                      "Check: lsof -i :%d", BRIDGE_PORT)
            raise
        except Exception as exc:
            log.error("[ERROR] Voice bridge server crashed: %s", exc, exc_info=True)
            raise


if __name__ == "__main__":
    bridge = SecureVoiceBridge()
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        log.info("Voice bridge stopped by user (KeyboardInterrupt).")
    except Exception as exc:
        log.error("[ERROR] Fatal bridge error: %s", exc, exc_info=True)
        raise SystemExit(1)
```

---

## 8. Phase 6 — Frontend Integration

### `frontend/src/services/voiceBridge.ts`

```typescript
/**
 * voiceBridge.ts
 * Manages the browser-side WebSocket connection to the host voice bridge.
 * Errors are caught at every async boundary — a broken bridge never
 * crashes the rest of the app.
 */

import toast from "react-hot-toast";

const BRIDGE_URL = "ws://localhost:9999";
const VOICE_TOKEN_URL = "/api/auth/voice-token";
const RECONNECT_DELAY = 5_000; // ms between reconnect attempts
const MAX_RECONNECTS = 5;

export type BridgeStatus =
  | "idle"
  | "connecting"
  | "active"
  | "error"
  | "offline";

export interface VoiceInteractionEvent {
  type: "voice_interaction";
  user: string;
  reply: string;
}

type MessageHandler = (event: VoiceInteractionEvent) => void;

class VoiceBridgeService {
  private ws: WebSocket | null = null;
  private voiceToken: string = "";
  private browserJwt: string = "";
  private reconnectCount = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  public status: BridgeStatus = "idle";
  public bridgeState: string = "idle";

  private statusListeners: Array<(s: BridgeStatus) => void> = [];
  private messageListeners: MessageHandler[] = [];

  // ── Public API ────────────────────────────────────────────────────────────

  /** Called from useVoiceBridge after login. */
  async connect(jwt: string): Promise<void> {
    this.browserJwt = jwt;
    this.reconnectCount = 0;
    await this._fetchVoiceToken();
    this._openSocket();
  }

  /** Called on logout or app unmount. */
  disconnect(): void {
    this._clearReconnectTimer();
    if (this.ws) {
      try {
        this.ws.send(JSON.stringify({ type: "logout" }));
      } catch {
        /* ignore — socket may already be closed */
      }
      this.ws.close();
      this.ws = null;
    }
    this.voiceToken = "";
    this._setStatus("idle");
  }

  onStatusChange(cb: (s: BridgeStatus) => void): () => void {
    this.statusListeners.push(cb);
    return () => {
      this.statusListeners = this.statusListeners.filter((l) => l !== cb);
    };
  }

  onVoiceInteraction(cb: MessageHandler): () => void {
    this.messageListeners.push(cb);
    return () => {
      this.messageListeners = this.messageListeners.filter((l) => l !== cb);
    };
  }

  // ── Token fetching ────────────────────────────────────────────────────────

  private async _fetchVoiceToken(): Promise<void> {
    try {
      const response = await fetch(VOICE_TOKEN_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.browserJwt}`,
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        // Not a fatal error — bridge will stay idle; warn user subtly
        console.warn(
          `[VoiceBridge] Could not fetch voice token (HTTP ${response.status}). ` +
            "Host voice will be unavailable.",
        );
        toast("Voice bridge unavailable — using browser-only mode.", {
          icon: "🎙️",
        });
        return;
      }

      const data = await response.json();
      this.voiceToken = data.voice_token ?? "";
      if (!this.voiceToken) {
        console.warn("[VoiceBridge] voice_token missing from response.");
      }
    } catch (err) {
      console.warn("[VoiceBridge] Failed to fetch voice token:", err);
      // Non-fatal: app continues without host voice
    }
  }

  // ── WebSocket lifecycle ───────────────────────────────────────────────────

  private _openSocket(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this._setStatus("connecting");
    let ws: WebSocket;

    try {
      ws = new WebSocket(BRIDGE_URL);
    } catch (err) {
      // Thrown synchronously if the URL is malformed
      console.warn("[VoiceBridge] Cannot construct WebSocket:", err);
      this._setStatus("offline");
      return;
    }

    ws.onopen = () => {
      console.info("[VoiceBridge] Connected to host bridge.");
      this.reconnectCount = 0;
      this._sendAuthDelegate(ws);
    };

    ws.onmessage = (event) => {
      this._handleMessage(event.data);
    };

    ws.onerror = (event) => {
      // onerror fires before onclose; just log — onclose handles reconnect
      console.warn("[VoiceBridge] WebSocket error:", event);
    };

    ws.onclose = (event) => {
      console.info(`[VoiceBridge] Disconnected (code=${event.code}).`);
      this.ws = null;

      if (this.status === "idle") return; // intentional disconnect

      if (this.reconnectCount < MAX_RECONNECTS) {
        this.reconnectCount++;
        console.info(
          `[VoiceBridge] Reconnecting in ${RECONNECT_DELAY / 1000}s ` +
            `(attempt ${this.reconnectCount}/${MAX_RECONNECTS})…`,
        );
        this._setStatus("connecting");
        this.reconnectTimer = setTimeout(
          () => this._openSocket(),
          RECONNECT_DELAY,
        );
      } else {
        console.warn(
          "[VoiceBridge] Max reconnect attempts reached — bridge offline.",
        );
        this._setStatus("offline");
        toast(
          "Host voice bridge is offline. Chat will continue in text mode.",
          { icon: "⚠️" },
        );
      }
    };

    this.ws = ws;
  }

  private _sendAuthDelegate(ws: WebSocket): void {
    if (!this.voiceToken) {
      // No voice token — still connected but bridge stays idle server-side
      this._setStatus("active"); // connected, but voice inactive
      return;
    }
    try {
      ws.send(
        JSON.stringify({
          type: "auth_delegate",
          browserJwt: this.browserJwt,
          voiceToken: this.voiceToken,
          expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
        }),
      );
    } catch (err) {
      console.warn("[VoiceBridge] Failed to send auth_delegate:", err);
    }
  }

  // ── Message handling ──────────────────────────────────────────────────────

  private _handleMessage(raw: string): void {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(raw);
    } catch {
      console.warn("[VoiceBridge] Non-JSON message from bridge:", raw);
      return;
    }

    const type = msg["type"] as string | undefined;

    switch (type) {
      case "bridge_activated":
        this._setStatus("active");
        break;
      case "voice_interaction":
        this.messageListeners.forEach((cb) => {
          try {
            cb(msg as unknown as VoiceInteractionEvent);
          } catch (err) {
            console.warn("[VoiceBridge] voice_interaction handler error:", err);
          }
        });
        break;
      case "state_change":
        this.bridgeState = (msg["state"] as string) ?? "idle";
        break;
      case "token_expired":
        toast("Voice session expired. Log in again to re-activate.", {
          icon: "🔑",
        });
        this._setStatus("idle");
        break;
      case "auth_error":
        console.warn("[VoiceBridge] Auth error from bridge:", msg["detail"]);
        toast(`Voice bridge: ${msg["detail"] ?? "auth error"}`, { icon: "⚠️" });
        this._setStatus("error");
        break;
      case "pong":
        break; // keepalive, no action needed
      default:
        console.debug("[VoiceBridge] Unhandled message type:", type);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  private _setStatus(status: BridgeStatus): void {
    this.status = status;
    this.statusListeners.forEach((cb) => {
      try {
        cb(status);
      } catch {
        /* ignore */
      }
    });
  }

  private _clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

export const voiceBridgeService = new VoiceBridgeService();
```

### `frontend/src/hooks/useVoiceBridge.ts`

```typescript
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import {
  voiceBridgeService,
  BridgeStatus,
  VoiceInteractionEvent,
} from "@/services/voiceBridge";

interface UseVoiceBridgeReturn {
  status: BridgeStatus;
  bridgeState: string;
  lastTranscription: string;
}

export function useVoiceBridge(
  onVoiceInteraction?: (e: VoiceInteractionEvent) => void,
): UseVoiceBridgeReturn {
  const { user } = useAuthStore();
  const [status, setStatus] = useState<BridgeStatus>(voiceBridgeService.status);
  const [bridgeState, setBridgeState] = useState(
    voiceBridgeService.bridgeState,
  );
  const [lastTranscription, setLast] = useState("");

  // Connect / disconnect when auth state changes
  useEffect(() => {
    if (user?.isAuthenticated && user.token) {
      voiceBridgeService.connect(user.token).catch((err) => {
        // connect() catches internally, but just in case
        console.warn("[useVoiceBridge] connect() threw:", err);
      });
    } else {
      voiceBridgeService.disconnect();
    }
    return () => voiceBridgeService.disconnect();
  }, [user?.isAuthenticated, user?.token]);

  // Subscribe to status changes
  useEffect(() => {
    const unsub = voiceBridgeService.onStatusChange(setStatus);
    return unsub;
  }, []);

  // Subscribe to voice_interaction events
  useEffect(() => {
    const unsub = voiceBridgeService.onVoiceInteraction((event) => {
      setLast(event.user);
      // Update bridgeState optimistically
      setBridgeState("waiting_for_wake_word");
      onVoiceInteraction?.(event);
    });
    return unsub;
  }, [onVoiceInteraction]);

  return { status, bridgeState, lastTranscription };
}
```

### `frontend/src/components/VoiceIndicator.tsx`

```tsx
import { Mic, MicOff, Loader2 } from "lucide-react";
import { BridgeStatus } from "@/services/voiceBridge";

interface Props {
  status: BridgeStatus;
  bridgeState: string;
}

const CONFIG: Record<
  BridgeStatus,
  { label: string; color: string; pulse: boolean }
> = {
  idle: { label: "Voice Idle", color: "text-gray-400", pulse: false },
  connecting: { label: "Connecting…", color: "text-yellow-400", pulse: true },
  active: { label: "Listening", color: "text-green-400", pulse: true },
  error: { label: "Bridge Error", color: "text-red-400", pulse: false },
  offline: { label: "Bridge Offline", color: "text-gray-500", pulse: false },
};

export function VoiceIndicator({ status, bridgeState }: Props) {
  const cfg = CONFIG[status] ?? CONFIG.offline;
  const label =
    bridgeState === "processing"
      ? "Processing…"
      : bridgeState === "speaking"
        ? "Speaking…"
        : cfg.label;

  return (
    <div
      className={`flex items-center gap-1.5 text-xs font-medium ${cfg.color}`}
      title={`Voice bridge: ${label}`}
    >
      {status === "connecting" ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : status === "offline" || status === "error" ? (
        <MicOff className="w-3.5 h-3.5" />
      ) : (
        <span className="relative flex h-2 w-2">
          {cfg.pulse && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                status === "active" ? "bg-green-400" : "bg-yellow-400"
              }`}
            />
          )}
          <Mic className="w-3.5 h-3.5" />
        </span>
      )}
      <span className="hidden sm:inline">{label}</span>
    </div>
  );
}
```

### ChatPage additions (`ChatPage.tsx`)

```tsx
// Add inside ChatPage, alongside existing message handling:
import { useVoiceBridge } from "@/hooks/useVoiceBridge";
import { VoiceInteractionEvent } from "@/services/voiceBridge";

// Inside the component:
const handleVoiceInteraction = useCallback(
  (event: VoiceInteractionEvent) => {
    try {
      // Append the voice exchange to the existing chat history
      appendMessage({ role: "user", content: event.user, source: "voice" });
      appendMessage({
        role: "assistant",
        content: event.reply,
        source: "voice",
      });
    } catch (err) {
      console.warn("[ChatPage] Failed to append voice interaction:", err);
    }
  },
  [appendMessage],
);

const { status: bridgeStatus, bridgeState } = useVoiceBridge(
  handleVoiceInteraction,
);
```

---

## 9. Phase 7 — Docker Compose Wiring

**Additions to `docker-compose.yml`**

```yaml
services:
  # ── Voice Bridge Host Setup (one-shot, voice profile only) ──────────────────
  host-setup:
    image: ubuntu:22.04
    network_mode: host
    profiles: [voice]
    volumes:
      - ./scripts:/scripts:ro
      - ./voice-bridge:/voice-bridge:ro
      - ~/.agentium:/root/.agentium
      - ~/.agentium-voice:/root/.agentium-voice
    environment:
      - HOME=/root
    command: >
      bash -c "
        echo '[host-setup] Starting OS detection...' &&
        bash /scripts/detect-host.sh &&
        echo '[host-setup] Starting dependency install...' &&
        bash /scripts/install-voice-bridge.sh &&
        echo '[host-setup] Done.'
      "
    restart: "no"
```

**`.env.example` additions**

```env
# ── Voice Bridge ───────────────────────────────────────────
VOICE_JWT_SECRET=change-me-to-a-random-32-character-string
VOICE_TOKEN_DURATION_MINUTES=30
WHATSAPP_BRIDGE_TOKEN=changeme
```

**`Makefile` additions**

```makefile
.PHONY: install-voice uninstall-voice voice-logs voice-status

install-voice:
	@echo "Running host-native voice bridge installer..."
	docker compose --profile voice up host-setup --abort-on-container-exit
	@echo "Done. Check ~/.agentium/install.log for details."

uninstall-voice:
	@bash scripts/uninstall-voice-bridge.sh

voice-logs:
	@case "$$(grep SVC_MGR ~/.agentium/env.conf | cut -d= -f2)" in \
	  systemd) journalctl --user -u agentium-voice -f ;; \
	  launchd)  tail -f ~/.agentium/voice-bridge.log ;; \
	  *)        tail -f ~/.agentium/voice-bridge.log ;; \
	esac

voice-status:
	@case "$$(grep SVC_MGR ~/.agentium/env.conf | cut -d= -f2)" in \
	  systemd) systemctl --user status agentium-voice ;; \
	  launchd)  launchctl list com.agentium.voice ;; \
	  wsl2)     ps aux | grep agentium-voice ;; \
	  *)        echo "Run manually: ps aux | grep main.py" ;; \
	esac
```

---

## 10. Error Handling Reference

Every layer has its own error boundary. The table below shows what happens in each failure scenario so you know the system never silently breaks.

| Layer                     | Failure                         | What Happens                                       | User Impact                                                    |
| ------------------------- | ------------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| `detect-host.sh`          | `uname` fails                   | Defaults to `linux`, logs `[WARN]`                 | Detection continues with safe fallback                         |
| `detect-host.sh`          | No Python ≥ 3.10                | Writes `PYTHON_BIN=python3_missing`, warns         | Installer skips venv creation; shows clear message             |
| `detect-host.sh`          | No microphone                   | Sets `HAS_MIC=false`, warns                        | Bridge starts; tells user at runtime when speech capture fails |
| `detect-host.sh`          | Docker gateway unknown          | Defaults to `172.17.0.1`, warns                    | User can edit `~/.agentium/env.conf` to correct                |
| `install-voice-bridge.sh` | `apt`/`brew` fails              | `run_or_warn` logs and continues                   | Individual packages may be missing; warned in log              |
| `install-voice-bridge.sh` | One pip package fails           | Warned per-package; rest install                   | Degraded feature (e.g. no Vosk offline fallback)               |
| `register-service.sh`     | `systemctl` fails               | Warns with manual start command                    | User starts bridge manually                                    |
| `register-service.sh`     | `launchctl` fails               | Warns with manual load command                     | User loads plist manually                                      |
| `main.py` import          | `pyttsx3` missing               | `TTS_AVAILABLE=False`, warns once                  | Bridge runs; replies printed to log, not spoken                |
| `main.py` import          | `SpeechRecognition` missing     | `SR_AVAILABLE=False`, warns once                   | Bridge runs; no voice capture; text chat unaffected            |
| `main.py`                 | Mic error (`OSError`)           | Warns with message, returns `None`                 | Loop skips capture; tries again next cycle                     |
| `main.py`                 | Google STT network error        | Falls back to Vosk; warns if Vosk also unavailable | Returns `None`; bridge tells user it didn't hear               |
| `main.py`                 | Backend `ConnectionError`       | Warns, returns `None` to listen loop               | Bridge speaks "having trouble reaching backend"                |
| `main.py`                 | Backend HTTP error              | Warns with status code, continues                  | Same as above                                                  |
| `main.py`                 | TTS engine crash                | Warns, returns without speaking                    | Reply shown in ChatPage only                                   |
| `main.py`                 | Browser WS message invalid JSON | Logs warning, ignores message                      | Other messages unaffected                                      |
| `main.py`                 | Port 9999 already in use        | Logs `[ERROR]` with hint, raises                   | User sees clear message; no silent hang                        |
| `voiceBridge.ts`          | `/auth/voice-token` fails       | Warns in console, shows toast                      | App continues in text-only mode                                |
| `voiceBridge.ts`          | WS connection refused           | Sets status `offline`, shows toast                 | Chat page fully functional; no voice                           |
| `voiceBridge.ts`          | WS drops mid-session            | Auto-reconnects up to 5×                           | Transparent to user if reconnects succeed                      |
| `voiceBridge.ts`          | Max reconnects reached          | Sets status `offline`, shows toast                 | User notified; text chat continues                             |
| `ChatPage.tsx`            | `appendMessage` throws          | Caught in `handleVoiceInteraction`                 | One message may be lost; page doesn't crash                    |
| `auth.py`                 | `VOICE_JWT_SECRET` not set      | Returns HTTP 503 with clear message                | Voice token unavailable; app logs warn                         |

---

> **Summary of install flow:**
> `make install-voice` → `docker compose --profile voice up host-setup` → `detect-host.sh` → `install-voice-bridge.sh` → `register-service.sh` → service starts on host → user opens browser → logs in → `voiceBridgeService.connect()` → voice token issued → bridge activated → say **"Agentium"** → talk to the Head of Council → hear the reply.

Check working for windows:

What Needs to Change for Windows 10/11

1. detect-host.sh → detect-host.ps1 or extend bash
   Your detect-host.sh uses uname, /proc/version, /etc/os-release — none exist on native Windows.
   Need to add Windows detection:
   powershell# detect-host.ps1
   $OS = "windows"
$PKG_MGR = "winget" # or choco
   $SVC_MGR = "windows_service"  # or task_scheduler
$PYTHON_BIN = (Get-Command python).Source
   $CONF_DIR = "$env:USERPROFILE\.agentium"
   Or in bash (if keeping one script), add to detect_os_family():
   bashMINGW*|CYGWIN*|MSYS*) echo "windows" ;;
   Your code already has MINGW*|CYGWIN\* → maps to wsl2 which is wrong for native Windows.

2. install-voice-bridge.sh → Add Windows branch
   System audio packages — instead of apt/brew:
   powershell# Option A: winget
   winget install -e --id Python.Python.3.11

# Option B: choco

choco install python portaudio
PyAudio is the hardest part on Windows:
powershell# Pre-built wheel is easiest
pip install pipwin
pipwin install pyaudio

# OR download wheel directly from:

# https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio

pip install PyAudio‑0.2.14‑cp311‑cp311‑win_amd64.whl

3. Service Registration — Replace systemd/launchd
   Windows has two options:
   Option A: Task Scheduler (simplest, no admin needed)
   powershell$action = New-ScheduledTaskAction -Execute "python" `
  -Argument "C:\Users\$env:USERNAME\.agentium\voice-bridge\main.py"
$trigger = New-ScheduledTaskTrigger -AtLogOn
   Register-ScheduledTask -TaskName "AgentiumVoiceBridge" `
   -Action $action -Trigger $trigger -RunLevel Limited
   Option B: Windows Service via NSSM (recommended)
   powershell# Install NSSM first
   choco install nssm
   nssm install AgentiumVoiceBridge python
   nssm set AgentiumVoiceBridge AppParameters "C:\path\to\main.py"
   nssm start AgentiumVoiceBridge

4. Path Issues in main.py and scripts
   Current (Unix)Windows equivalentPath.home() / ".agentium"✅ Works — pathlib is cross-platform~/.agentium/env.conf%USERPROFILE%\.agentium\env.conf#!/usr/bin/env bash❌ Doesn't exist natively$CONF_DIR/voice-venv/bin/python%CONF_DIR%\voice-venv\Scripts\python.exe
main.py is mostly fine — pathlib.Path works on Windows. The one fix needed:
python# Current - breaks on Windows:
VENV_PYTHON = "$VENV_DIR/bin/python"

# Fix - detect platform:

import platform
VENV_PYTHON = (
Path.home() / ".agentium" / "voice-venv" / "Scripts" / "python.exe"
if platform.system() == "Windows"
else Path.home() / ".agentium" / "voice-venv" / "bin" / "python"
)

5. TTS on Windows
   pyttsx3 works on Windows out of the box (uses SAPI5) — no changes needed.
6. Microphone on Windows
   SpeechRecognition + PyAudio work on Windows once installed. No ALSA needed — Windows uses its own audio stack.
   Add to detect-host.sh Windows branch:
   bash# Skip arecord check on Windows — use a Python check instead
   HAS_MIC="true" # Let PyAudio handle it at runtime

```

---

## Recommended Approach: Two Files

Rather than rewriting everything, the cleanest path is:
```

scripts/
detect-host.sh ← Linux/macOS/WSL2 (current)
detect-host.ps1 ← Windows NEW
install-voice-bridge.sh ← Linux/macOS/WSL2 (current)  
 install-voice-bridge.ps1← Windows NEW
uninstall-voice-bridge.sh
uninstall-voice-bridge.ps1 ← Windows NEW
And a single entry-point that detects and routes:
powershell# setup.ps1 — Windows entry point
Write-Host "=== Agentium Voice Bridge Windows Installer ==="
& "$PSScriptRoot\scripts\detect-host.ps1"
& "$PSScriptRoot\scripts\install-voice-bridge.ps1"

Summary of Work Required
TaskEffortdetect-host.ps1~50 linesinstall-voice-bridge.ps1~80 linesuninstall-voice-bridge.ps1~30 linesFix venv path in scripts~5 linesPyAudio install workaround~10 linesService via Task Scheduler or NSSM~20 linesmain.py path fix~5 lines
Total: ~200 lines of new PowerShell + minor Python fix. main.py needs almost no changes since pathlib and asyncio are cross-platform. The bulk of the work is the installer/detector scripts.
Want me to write these PowerShell scripts?
