#!/usr/bin/env bash
# =============================================================================
# scripts/voice-autoinstall.sh
# Runs inside the voice-autoinstall Docker container.
#
# Unix hosts (Linux / macOS / WSL2):
#   Installs Python deps + registers the OS service directly. Starts immediately.
#
# Windows hosts (Docker Desktop):
#   Cannot exec PowerShell on the host from a Linux container, so instead:
#   1. Writes bootstrap-voice.cmd  -> %USERPROFILE%\.agentium\
#   2. Copies agentium-voice-startup.cmd -> Windows Startup folder (auto-start on login)
#   3. Writes "Install Agentium Voice Bridge.cmd" -> Windows Desktop (manual start)
#   The real install runs later on the host via setup.ps1. The host installer
#   (install-voice-bridge.ps1) creates voice-installed.marker on success; this
#   container MUST NOT create it (doing so would disable every auto-prompt/guard).
# =============================================================================
set -euo pipefail

# ── Detect OS first so AGENTIUM_DIR and MARKER resolve to the right location ──
# On Windows the files must land in the Windows user profile (/host_home is
# mounted from ${USERPROFILE}), NOT in the ephemeral container filesystem.
IS_WINDOWS=false
if [ -d "/host_home/AppData" ]; then
    IS_WINDOWS=true
fi

if [ "$IS_WINDOWS" = "true" ]; then
    AGENTIUM_DIR="/host_home/.agentium"
else
    AGENTIUM_DIR="/root/.agentium"
fi

MARKER="$AGENTIUM_DIR/voice-installed.marker"
mkdir -p "$AGENTIUM_DIR"

echo "[voice-autoinstall] Backend is healthy. Checking install state..."

if [ -f "$MARKER" ]; then
    echo "[voice-autoinstall] Already installed -- skipping."
    echo "[voice-autoinstall] Delete ${AGENTIUM_DIR}/voice-installed.marker to force reinstall."
    exit 0
fi

# =============================================================================
# WINDOWS PATH
# =============================================================================
if [ "$IS_WINDOWS" = "true" ]; then
    echo "[voice-autoinstall] Windows host detected."

    # -- Resolve Windows repo root from Docker Desktop mount ------------------
    SCRIPTS_SRC=$(awk '$2=="/scripts"{print $1}' /proc/mounts 2>/dev/null | head -1 || true)
    echo "[voice-autoinstall] DEBUG: /scripts mount source = '$SCRIPTS_SRC'"
    echo "[voice-autoinstall] DEBUG: /proc/mounts lines matching scripts:"
    awk '$2~"scripts"' /proc/mounts 2>/dev/null | head -5 || echo "(none)"

    WIN_REPO=""
    UNIX_REPO=""
    if echo "$SCRIPTS_SRC" | grep -qE "^/run/desktop/mnt/host/"; then
        echo "[voice-autoinstall] Matched pattern: /run/desktop/mnt/host/"
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|/run/desktop/mnt/host/||; s|/scripts$||')
        DRIVE=$(echo "$UNIX_REPO" | cut -d/ -f1 | tr '[:lower:]' '[:upper:]')
        REST=$(echo "$UNIX_REPO" | cut -d/ -f2- | tr '/' '\\')
        WIN_REPO="${DRIVE}:\\${REST}"
    elif echo "$SCRIPTS_SRC" | grep -qE "^/host_mnt/"; then
        echo "[voice-autoinstall] Matched pattern: /host_mnt/"
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|/host_mnt/||; s|/scripts$||')
        DRIVE=$(echo "$UNIX_REPO" | cut -d/ -f1 | tr '[:lower:]' '[:upper:]')
        REST=$(echo "$UNIX_REPO" | cut -d/ -f2- | tr '/' '\\')
        WIN_REPO="${DRIVE}:\\${REST}"
    elif echo "$SCRIPTS_SRC" | grep -qE "^//wsl\.localhost/"; then
        echo "[voice-autoinstall] Matched pattern: //wsl.localhost/"
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|^//wsl\.localhost/[^/]*/||; s|/scripts$||')
        WIN_REPO=$(wslpath -w "/$UNIX_REPO" 2>/dev/null || echo "")
    elif echo "$SCRIPTS_SRC" | grep -qE "^/mnt/"; then
        echo "[voice-autoinstall] Matched pattern: /mnt/"
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|/scripts$||')
        DRIVE=$(echo "$UNIX_REPO" | cut -d/ -f1 | cut -c2-3 | tr '[:lower:]' '[:upper:]')
        REST=$(echo "$UNIX_REPO" | cut -d/ -f2- | tr '/' '\\')
        WIN_REPO="${DRIVE}:\\${REST}"
    else
        # Generic fallback: check /proc/mounts for any Docker-style mount of scripts
        echo "[voice-autoinstall] No standard pattern matched — trying generic detection"
        for src in $(awk '$2=="/scripts"{print $1}' /proc/mounts 2>/dev/null); do
            # Skip non-path sources (tmpfs, overlay, etc.)
            echo "$src" | grep -qE "^/" || continue
            # Try to extract a Windows path from any remaining pattern
            # Strip common prefixes
            CLEAN=$(echo "$src" | sed 's|^/run/desktop/mnt/host/||; s|^/host_mnt/||; s|^/mnt/||')
            if [ "$CLEAN" != "$src" ]; then
                DRIVE=$(echo "$CLEAN" | cut -d/ -f1 | tr '[:lower:]' '[:upper:]')
                REST=$(echo "$CLEAN" | cut -d/ -f2- | tr '/' '\\' | sed 's|\\scripts$||')
                WIN_REPO="${DRIVE}:\\${REST}"
                break
            fi
        done
    fi

    if [ -z "$WIN_REPO" ]; then
        echo "[voice-autoinstall] WARN: Could not auto-detect repo root — bootstrap will search for it"
        echo "[voice-autoinstall]        Run setup.ps1 directly from PowerShell:"
        echo "[voice-autoinstall]          powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1"
        WIN_REPO=''
        # Write minimal env.conf — setup.ps1 will update values
        echo "BACKEND_URL=http://127.0.0.1:8000" > "$AGENTIUM_DIR/env.conf"
        echo "WS_PORT=9999" >> "$AGENTIUM_DIR/env.conf"
        echo "WAKE_WORD=agentium" >> "$AGENTIUM_DIR/env.conf"
        echo "IS_WINDOWS=true" >> "$AGENTIUM_DIR/env.conf"
    else
        echo "[voice-autoinstall] Resolved Windows repo root: $WIN_REPO"
        echo "REPO_ROOT=$WIN_REPO" > "$AGENTIUM_DIR/env.conf"
        echo "BACKEND_URL=http://127.0.0.1:8000" >> "$AGENTIUM_DIR/env.conf"
        echo "WS_PORT=9999" >> "$AGENTIUM_DIR/env.conf"
        echo "WAKE_WORD=agentium" >> "$AGENTIUM_DIR/env.conf"
        echo "IS_WINDOWS=true" >> "$AGENTIUM_DIR/env.conf"
    fi

    STARTUP_DIR="/host_home/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"

    # -- 1. bootstrap-voice.cmd (runs setup.ps1 with UAC on demand) -----------
    BOOTSTRAP_TEMPLATE="/scripts/windows-bootstrap.cmd"
    BOOTSTRAP_DEST="$AGENTIUM_DIR/bootstrap-voice.cmd"
    if [ -f "$BOOTSTRAP_TEMPLATE" ]; then
        sed "s|AGENTIUM_REPO_ROOT|${WIN_REPO}|g" "$BOOTSTRAP_TEMPLATE" > "$BOOTSTRAP_DEST"
    else
        printf '@echo off\r\nsetlocal\r\nset LOG=%%USERPROFILE%%\\.agentium\\bootstrap.log\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%s\\scripts\\setup.ps1" >> "%%LOG%%" 2>&1\r\n' \
            "$WIN_REPO" > "$BOOTSTRAP_DEST"
    fi
    echo "[voice-autoinstall] bootstrap-voice.cmd written."

    # -- 2. Single Startup launcher (template already guards on marker) -------
    if [ -d "$STARTUP_DIR" ]; then
        cp "/scripts/agentium-voice-startup.cmd" "$STARTUP_DIR/agentium-voice-startup.cmd"
        echo "[voice-autoinstall] Startup launcher written."
    else
        echo "[voice-autoinstall] WARN: Startup folder not found -- bridge will not auto-start on login."
    fi

    # -- 3. Desktop shortcut for immediate manual install ---------------------
    DESKTOP_DIR="/host_home/Desktop"
    if [ -d "$DESKTOP_DIR" ]; then
        printf '@echo off\r\nstart "" /min cmd /c "%%USERPROFILE%%\\.agentium\\bootstrap-voice.cmd"\r\n' \
            > "$DESKTOP_DIR/Install Agentium Voice Bridge.cmd"
        echo "[voice-autoinstall] Desktop shortcut written."
    fi

    echo ""
    echo "[voice-autoinstall] ================================================================"
    echo "[voice-autoinstall]  Windows setup complete."
    echo "[voice-autoinstall]  Installs on next login (UAC prompt once),"
    echo "[voice-autoinstall]  or double-click: Desktop\\Install Agentium Voice Bridge.cmd"
    echo "[voice-autoinstall]"
    echo "[voice-autoinstall]  The Desktop UI companion (system tray + waveform overlay)"
    echo "[voice-autoinstall]  will install automatically alongside the voice bridge."
    echo "[voice-autoinstall] ================================================================"

# =============================================================================
# UNIX PATH (Linux / macOS / WSL2)
# =============================================================================
else
    echo "[voice-autoinstall] Unix host detected."

    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq bash curl python3 python3-venv python3-pip > /dev/null 2>&1

    echo "[voice-autoinstall] Running OS detection..."
    bash /scripts/detect-host.sh

    echo "[voice-autoinstall] Installing voice bridge..."
    bash /scripts/install-voice-bridge.sh

    echo "[voice-autoinstall] Voice bridge installed and running."
    echo "[voice-autoinstall] Desktop UI companion installed (macOS: launchd agent, Linux: nohup)."
fi

echo "[voice-autoinstall] Done. The host installer creates voice-installed.marker on success."
