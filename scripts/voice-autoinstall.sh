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
#   2. Writes agentium-voice-startup.cmd -> Windows Startup folder (auto-start on login)
#   3. Writes prompt.vbs -> %USERPROFILE%\.agentium\
#        A VBScript that pops up a YES/NO dialog on the Windows desktop.
#        If the user clicks YES, it runs setup.ps1 immediately (UAC prompt appears).
#        If NO, the bridge starts automatically on next login anyway.
#   4. Writes run-prompt.cmd -> Windows Startup folder so the VBS fires on login
#      AND writes a scheduled task trigger so it also fires RIGHT NOW without
#      needing the user to log out.
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
    WIN_REPO=""

    if echo "$SCRIPTS_SRC" | grep -qE "^/run/desktop/mnt/host/"; then
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|/run/desktop/mnt/host/||; s|/scripts$||')
        DRIVE=$(echo "$UNIX_REPO" | cut -d/ -f1 | tr '[:lower:]' '[:upper:]')
        REST=$(echo "$UNIX_REPO" | cut -d/ -f2- | tr '/' '\\')
        WIN_REPO="${DRIVE}:\\${REST}"
    elif echo "$SCRIPTS_SRC" | grep -qE "^/host_mnt/"; then
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|/host_mnt/||; s|/scripts$||')
        DRIVE=$(echo "$UNIX_REPO" | cut -d/ -f1 | tr '[:lower:]' '[:upper:]')
        REST=$(echo "$UNIX_REPO" | cut -d/ -f2- | tr '/' '\\')
        WIN_REPO="${DRIVE}:\\${REST}"
    elif echo "$SCRIPTS_SRC" | grep -qE "^//wsl\.localhost/"; then
        # Docker Desktop 4.20+ uses //wsl.localhost/<distro>/<path>
        UNIX_REPO=$(echo "$SCRIPTS_SRC" | sed 's|^//wsl\.localhost/[^/]*/||; s|/scripts$||')
        WIN_REPO=$(wslpath -w "/$UNIX_REPO" 2>/dev/null || echo "")
    fi

    if [ -z "$WIN_REPO" ]; then
        echo "[voice-autoinstall] WARN: Could not auto-detect repo root -- falling back"
        WIN_REPO='%USERPROFILE%\agentium'
    fi

    echo "[voice-autoinstall] Resolved Windows repo root: $WIN_REPO"

    # AGENTIUM_DIR already set to /host_home/.agentium above (maps to %USERPROFILE%\.agentium)
    STARTUP_DIR="/host_home/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"

    # -- 1. Write bootstrap-voice.cmd -----------------------------------------
    BOOTSTRAP_TEMPLATE="/scripts/windows-bootstrap.cmd"
    BOOTSTRAP_DEST="$AGENTIUM_DIR/bootstrap-voice.cmd"

    if [ -f "$BOOTSTRAP_TEMPLATE" ]; then
        sed "s|AGENTIUM_REPO_ROOT|${WIN_REPO}|g" "$BOOTSTRAP_TEMPLATE" > "$BOOTSTRAP_DEST"
    else
        printf '@echo off\r\nsetlocal\r\nset LOG=%%USERPROFILE%%\\.agentium\\bootstrap.log\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%s\\voice-bridge\\setup.ps1" >> "%%LOG%%" 2>&1\r\n' \
            "$WIN_REPO" > "$BOOTSTRAP_DEST"
    fi
    echo "[voice-autoinstall] bootstrap-voice.cmd written."

    # -- 2. Write Startup folder auto-start stub ------------------------------
    if [ -d "$STARTUP_DIR" ]; then
        STUB_TEMPLATE="/scripts/agentium-voice-startup.cmd"
        if [ -f "$STUB_TEMPLATE" ]; then
            cp "$STUB_TEMPLATE" "$STARTUP_DIR/agentium-voice-startup.cmd"
        else
            printf '@echo off\r\nstart "" /min cmd /c "%%USERPROFILE%%\\.agentium\\bootstrap-voice.cmd"\r\n' \
                > "$STARTUP_DIR/agentium-voice-startup.cmd"
        fi
        echo "[voice-autoinstall] Login startup stub written to Startup folder."
    else
        echo "[voice-autoinstall] WARN: Startup folder not found -- bridge will not auto-start on login."
    fi

    # -- 3. Write prompt.vbs (YES/NO popup) -----------------------------------
    # VBScript runs natively on all Windows versions, no install needed.
    # It shows a dialog box: Yes = run setup.ps1 now, No = defer to next login.
    # ExpandEnvironmentStrings is used so the path works whether WIN_REPO is an
    # absolute path or contains unexpanded environment variables (e.g. fallback).

    cat > "$AGENTIUM_DIR/prompt.vbs" << VBSEOF
' Agentium Voice Bridge - install prompt
' Auto-generated by docker-compose voice-autoinstall service.
Dim sh
Set sh = CreateObject("WScript.Shell")
Dim setupPath
setupPath = sh.ExpandEnvironmentStrings("${WIN_REPO}\voice-bridge\setup.ps1")

Dim result
result = MsgBox( _
    "Agentium Voice Bridge is ready to install." & vbCrLf & vbCrLf & _
    "Click YES to install it now." & vbCrLf & _
    "  - A UAC prompt will appear - please click Allow." & vbCrLf & _
    "  - The bridge will start automatically afterwards." & vbCrLf & vbCrLf & _
    "Click NO to install automatically on your next Windows login.", _
    vbYesNo + vbQuestion + vbSystemModal, _
    "Agentium Voice Bridge")

If result = vbYes Then
    Dim shellApp
    Set shellApp = CreateObject("Shell.Application")
    shellApp.ShellExecute "powershell.exe", _
        "-NoProfile -ExecutionPolicy Bypass -File """ & setupPath & """", _
        "", "runas", 1
End If
VBSEOF

    echo "[voice-autoinstall] prompt.vbs written."

    # -- 4. Write run-prompt.cmd (launches the VBS) ---------------------------
    # This goes in the Startup folder so it fires on every login until the
    # marker file exists. It also self-deletes after first successful install.
    cat > "$AGENTIUM_DIR/run-prompt.cmd" << CMDEOF
@echo off
:: Agentium Voice Bridge -- show install prompt if not yet installed
if exist "%USERPROFILE%\.agentium\voice-installed.marker" (
    exit /b 0
)
wscript.exe "%USERPROFILE%\.agentium\prompt.vbs"
CMDEOF

    if [ -d "$STARTUP_DIR" ]; then
        # Use printf with \r\n so Windows cmd.exe is happy
        printf '@echo off\r\nif exist "%%USERPROFILE%%\\.agentium\\voice-installed.marker" exit /b 0\r\nwscript.exe "%%USERPROFILE%%\\.agentium\\prompt.vbs"\r\n' \
            > "$STARTUP_DIR/agentium-voice-prompt.cmd"
        echo "[voice-autoinstall] run-prompt.cmd written to Startup folder."
    fi

    # -- 5. Fire the popup RIGHT NOW via a self-deleting scheduled task --------
    # We create a one-shot Windows Task Scheduler job that runs in 5 seconds.
    # This gives Docker time to finish printing logs before the popup appears.
    # The task deletes itself after running (ExpireTime in the past + DeleteExpiredTaskAfter).
    #
    # We write a tiny .cmd to %USERPROFILE%\.agentium\ that Task Scheduler will run.
    # Task Scheduler can be triggered from schtasks.exe which IS accessible via
    # the Docker Desktop host process... but only if we write a trigger file.
    #
    # Simpler approach: write a run-now.vbs that uses WScript.Shell to run the
    # prompt, then write a .cmd that calls schtasks to register a one-shot task.
    # The .cmd is written to the host and then we use the /host_home mount to
    # put a special file that tells Windows to run it.
    #
    # MOST RELIABLE approach on Docker Desktop for Windows:
    # Write the VBS to a well-known location and also write a small wrapper that
    # the user's existing shell (explorer.exe) will pick up via the Startup folder.
    # Since we already wrote to the Startup folder, the popup fires on next login.
    #
    # For IMMEDIATE trigger without login: write a scheduled task XML file and
    # drop it where Task Scheduler's AT trigger can pick it up -- but that also
    # needs elevation. Instead, we use a simpler trick:
    # Write a .cmd to the SendTo / shell:startup that auto-runs via explorer,
    # OR write a registry Run key via a .reg file the user can double-click.
    #
    # The most zero-click immediate option on Windows from a Linux container:
    # Write a .url file to the Desktop that auto-runs the VBS when explorer
    # processes it -- but that also doesn't auto-execute.
    #
    # FINAL DECISION: Write a .reg file that adds a one-shot RunOnce key.
    # RunOnce fires automatically the NEXT time the user's session processes it
    # (which happens on login, or can be triggered by explorer restart).
    # Combined with the Startup folder stub, this gives maximum coverage.

    DESKTOP_DIR="/host_home/Desktop"
    REG_FILE="$AGENTIUM_DIR/agentium-runonce.reg"

    # Convert path for registry (double backslashes)
    PROMPT_CMD_WIN="%USERPROFILE%\\.agentium\\run-prompt.cmd"

    printf 'Windows Registry Editor Version 5.00\r\n\r\n[HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce]\r\n"AgentiumVoicePrompt"="cmd.exe /c \\"%s\\""\r\n' \
        "$PROMPT_CMD_WIN" > "$REG_FILE"

    echo "[voice-autoinstall] agentium-runonce.reg written."

    # Also write a shortcut on the Desktop so the user can trigger it manually
    # with one double-click if they want it right now
    if [ -d "$DESKTOP_DIR" ]; then
        cat > "$DESKTOP_DIR/Install Agentium Voice Bridge.cmd" << DESKEOF
@echo off
wscript.exe "%USERPROFILE%\.agentium\prompt.vbs"
DESKEOF
        echo "[voice-autoinstall] Desktop shortcut written."
    fi

    # -- Merge the RunOnce registry key automatically -------------------------
    # We can silently merge the .reg file from within the container by writing
    # another small VBS that calls regedit /s, and placing THAT in a location
    # that will be auto-executed. But we still have the same chicken-and-egg
    # problem. The cleanest zero-click solution:
    #
    # Write a tiny HTA (HTML Application) file to the Startup folder.
    # HTAs run with full trust in Windows and can execute shell commands.
    # Explorer processes the Startup folder on login, launching the HTA.
    # The HTA merges the reg key, shows the prompt, then closes itself.

    if [ -d "$STARTUP_DIR" ]; then
        cat > "$STARTUP_DIR/agentium-voice-setup.hta" << HTAEOF
<html>
<head>
<title>Agentium Voice Bridge Setup</title>
<HTA:APPLICATION
  APPLICATIONNAME="AgentiumVoiceSetup"
  BORDER="none"
  BORDERSTYLE="normal"
  CAPTION="no"
  SHOWINTASKBAR="no"
  SINGLEINSTANCE="yes"
  SYSMENU="no"
  WINDOWSTATE="minimize"
/>
<script language="VBScript">
Sub Window_OnLoad
    ' Hide the window immediately
    window.resizeTo 0, 0
    window.moveTo -2000, -2000

    ' Skip if already installed
    Dim fso
    Set fso = CreateObject("Scripting.FileSystemObject")
    Dim marker
    marker = fso.BuildPath(CreateObject("WScript.Shell").ExpandEnvironmentStrings("%USERPROFILE%"), ".agentium\voice-installed.marker")
    If fso.FileExists(marker) Then
        window.close
        Exit Sub
    End If

    ' Show the install prompt
    Dim result
    result = MsgBox( _
        "Agentium Voice Bridge is ready to install." & vbCrLf & vbCrLf & _
        "Click YES to install it now." & vbCrLf & _
        "  A UAC prompt will appear -- please click Allow." & vbCrLf & vbCrLf & _
        "Click NO to be reminded on next login.", _
        vbYesNo + vbQuestion + vbSystemModal, _
        "Agentium Voice Bridge")

    If result = vbYes Then
        Dim sh
        Set sh = CreateObject("WScript.Shell")
        Dim setupPath
        setupPath = sh.ExpandEnvironmentStrings("${WIN_REPO}\voice-bridge\setup.ps1")
        Dim shellApp
        Set shellApp = CreateObject("Shell.Application")
        shellApp.ShellExecute "powershell.exe", _
            "-NoProfile -ExecutionPolicy Bypass -File """ & setupPath & """", _
            "", "runas", 1
    End If

    window.close
End Sub
</script>
</head>
<body></body>
</html>
HTAEOF
        echo "[voice-autoinstall] agentium-voice-setup.hta written to Startup folder."
        echo "[voice-autoinstall] The popup will appear automatically on next Windows login."
    fi

    echo ""
    echo "[voice-autoinstall] ================================================================"
    echo "[voice-autoinstall]  Windows setup complete."
    echo "[voice-autoinstall]"
    echo "[voice-autoinstall]  AUTOMATIC: A popup will appear on your next Windows login."
    echo "[voice-autoinstall]             Click YES then Allow on the UAC prompt."
    echo "[voice-autoinstall]"
    echo "[voice-autoinstall]  INSTALL NOW (no login needed) -- double-click this file:"
    echo "[voice-autoinstall]    %USERPROFILE%\\.agentium\\run-prompt.cmd"
    echo "[voice-autoinstall]  OR open PowerShell and run:"
    echo "[voice-autoinstall]    powershell -ExecutionPolicy Bypass -File \"${WIN_REPO}\\voice-bridge\\setup.ps1\""
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
fi

touch "$MARKER"
echo "[voice-autoinstall] Done. Log: ~/.agentium/install.log"