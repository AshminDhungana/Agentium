#!/usr/bin/env bash
# =============================================================================
# scripts/detect-host.sh  — Agentium OS probe
# Writes ~/.agentium/env.conf  (KEY=VALUE pairs consumed by installer + bridge)
# Every check is independent: a failure writes a safe default and warns.
# =============================================================================
set -euo pipefail

CONF_DIR="$HOME/.agentium"
CONF_FILE="$CONF_DIR/env.conf"
LOG_FILE="$CONF_DIR/detect.log"
WARN_COUNT=0

mkdir -p "$CONF_DIR"
: > "$CONF_FILE"
: > "$LOG_FILE"

# ── helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[WARN]  $*" | tee -a "$LOG_FILE" >&2; WARN_COUNT=$((WARN_COUNT+1)); }
conf() { echo "$1=$2" >> "$CONF_FILE"; }
safe_conf() {
  local key="$1" val="$2" fallback="$3"
  if [[ -z "$val" ]]; then
    warn "Could not detect $key — using fallback: $fallback"
    conf "$key" "$fallback"
  else
    conf "$key" "$val"
  fi
}

log "=== Agentium OS Detection Started ==="

# ── Step 1.1  OS family ────────────────────────────────────────────────────────
log "Step 1.1 — Detecting OS family"
detect_os_family() {
  local uname
  uname=$(uname -s 2>/dev/null) || { warn "uname failed; defaulting to linux"; echo "linux"; return; }
  case "$uname" in
    Darwin)  echo "macos" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then echo "wsl2"
      else echo "linux"
      fi ;;
    MINGW*|CYGWIN*) echo "wsl2" ;;
    *) warn "Unknown OS '$uname'; defaulting to linux"; echo "linux" ;;
  esac
}
OS_FAMILY=$(detect_os_family)
conf "OS_FAMILY" "$OS_FAMILY"
log "  OS_FAMILY=$OS_FAMILY"

# ── Step 1.2  Linux distro ─────────────────────────────────────────────────────
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

# ── Step 1.3  Package manager ──────────────────────────────────────────────────
log "Step 1.3 — Selecting package manager"
detect_pkg_mgr() {
  case "$OS_FAMILY" in
    macos)
      command -v brew &>/dev/null && echo "brew" || { warn "Homebrew not found"; echo "brew_missing"; } ;;
    linux|wsl2)
      case "$DISTRO" in
        ubuntu|debian|linuxmint|pop) echo "apt" ;;
        fedora|rhel|centos|rocky)    echo "dnf" ;;
        arch|manjaro|endeavouros)    echo "pacman" ;;
        opensuse*)                   echo "zypper" ;;
        *) warn "Unknown distro '$DISTRO'; defaulting to apt"; echo "apt" ;;
      esac ;;
    *) warn "Cannot select pkg manager for OS_FAMILY=$OS_FAMILY"; echo "unknown" ;;
  esac
}
PKG_MGR=$(detect_pkg_mgr)
conf "PKG_MGR" "$PKG_MGR"
log "  PKG_MGR=$PKG_MGR"

# ── Step 1.4  Python ───────────────────────────────────────────────────────────
log "Step 1.4 — Locating Python ≥ 3.10"
find_python() {
  for candidate in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" &>/dev/null; then
      local ver
      ver=$("$candidate" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null) || continue
      [[ "$ver" == "True" ]] && { echo "$candidate"; return; }
    fi
  done
  echo ""
}
PYTHON_BIN=$(find_python)
if [[ -z "$PYTHON_BIN" ]]; then
  warn "No Python ≥ 3.10 found — voice bridge venv will not be created"
  conf "PYTHON_BIN" "python3_missing"
else
  conf "PYTHON_BIN" "$PYTHON_BIN"
  log "  PYTHON_BIN=$PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"
fi

# ── Step 1.5  Microphone ──────────────────────────────────────────────────────
log "Step 1.5 — Checking microphone"
HAS_MIC="false"
case "$OS_FAMILY" in
  macos)
    # On macOS we rely on the OS granting mic permission at runtime
    HAS_MIC="true" ;;
  linux|wsl2)
    if command -v arecord &>/dev/null && arecord -l 2>/dev/null | grep -q "card"; then
      HAS_MIC="true"
    else
      warn "No ALSA capture device found — voice capture may fail at runtime"
    fi ;;
esac
conf "HAS_MIC" "$HAS_MIC"
log "  HAS_MIC=$HAS_MIC"

# ── Step 1.6  Docker gateway (backend URL) ─────────────────────────────────────
log "Step 1.6 — Detecting Docker gateway"
DOCKER_GW="172.17.0.1"   # safe default
if command -v docker &>/dev/null; then
  GW=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || true)
  [[ -n "$GW" ]] && DOCKER_GW="$GW"
fi
BACKEND_URL="http://${DOCKER_GW}:8000"
conf "BACKEND_URL" "$BACKEND_URL"
log "  BACKEND_URL=$BACKEND_URL"

# ── Step 1.7  Service manager ─────────────────────────────────────────────────
log "Step 1.7 — Detecting service manager"
detect_svc_mgr() {
  case "$OS_FAMILY" in
    macos)  echo "launchd" ;;
    linux)  systemctl --user status &>/dev/null && echo "systemd" || echo "none" ;;
    wsl2)   echo "wsl2" ;;
    *)      echo "none" ;;
  esac
}
SVC_MGR=$(detect_svc_mgr)
conf "SVC_MGR" "$SVC_MGR"
log "  SVC_MGR=$SVC_MGR"

# ── Step 1.8  WS port ─────────────────────────────────────────────────────────
conf "WS_PORT" "9999"
conf "WAKE_WORD" "agentium"

# ── Summary ────────────────────────────────────────────────────────────────────
log "=== Detection complete — $WARN_COUNT warning(s) — written to $CONF_FILE ==="