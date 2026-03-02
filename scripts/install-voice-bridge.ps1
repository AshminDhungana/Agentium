# scripts/install-voice-bridge.ps1 - Agentium voice bridge installer (Windows)
# Reads $env:USERPROFILE\.agentium\env.conf written by detect-host.ps1
# Supports two launch strategies:
#   task_scheduler — real Python install, uses Windows Task Scheduler (original)
#   vbs_startup    — Windows Store Python, uses VBScript + Startup folder shortcut
# NOTE: Called from setup.ps1 which already handles UAC elevation.

param(
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Continue"

$CONF_DIR  = Join-Path $env:USERPROFILE ".agentium"
$CONF_FILE = Join-Path $CONF_DIR "env.conf"
$LOG_FILE  = Join-Path $CONF_DIR "install.log"
$VENV_DIR  = Join-Path $CONF_DIR "voice-venv"

New-Item -ItemType Directory -Force -Path $CONF_DIR | Out-Null
"" | Set-Content $LOG_FILE

function Write-Log($msg) {
    $ts   = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $LOG_FILE -Value $line
    Write-Host $line
}

function Write-Warn($msg) {
    $line = "[WARN] $msg"
    Add-Content -Path $LOG_FILE -Value $line
    Write-Warning $msg
}

function Run-Or-Warn($label, [scriptblock]$block) {
    try {
        $out = & $block 2>&1
        $out | ForEach-Object { Add-Content -Path $LOG_FILE -Value "$_" }
        Write-Log "  OK: $label"
        return $true
    } catch {
        Write-Warn "$label failed: $_"
        return $false
    }
}

# --- Load env.conf -----------------------------------------------------------
if (-not (Test-Path $CONF_FILE)) {
    Write-Warn "env.conf not found -- run detect-host.ps1 first"
    exit 1
}

$conf = @{}
Get-Content $CONF_FILE | ForEach-Object {
    if ($_ -match "^([^#=]+)=(.*)$") {
        $conf[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$PYTHON_BIN      = $conf["PYTHON_BIN"]
$BACKEND_URL     = $conf["BACKEND_URL"]
$IS_STORE_PYTHON = $conf["IS_STORE_PYTHON"]
$SVC_MGR         = $conf["SVC_MGR"]

# Resolve REPO_ROOT
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = $conf["REPO_ROOT"] }
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $candidate = Split-Path $PSScriptRoot -Parent
    if (Test-Path (Join-Path $candidate "voice-bridge\main.py")) { $RepoRoot = $candidate }
}

$BRIDGE_DIR = if ($RepoRoot) { Join-Path $RepoRoot "voice-bridge" } else { "" }
$MainPy     = if ($BRIDGE_DIR) { Join-Path $BRIDGE_DIR "main.py" } else { "" }

Write-Log "=== Agentium Voice Bridge Installer (Windows) ==="
Write-Log "REPO_ROOT=$RepoRoot"
Write-Log "PYTHON_BIN=$PYTHON_BIN"
Write-Log "IS_STORE_PYTHON=$IS_STORE_PYTHON"
Write-Log "SVC_MGR=$SVC_MGR"
Write-Log "BACKEND_URL=$BACKEND_URL"

if ($MainPy -and -not (Test-Path $MainPy)) {
    Write-Warn "main.py not found at $MainPy -- check REPO_ROOT in $CONF_FILE"
} else {
    Write-Log "  main.py found at $MainPy"
}

# --- Step 2.1  System audio --------------------------------------------------
Write-Log "Step 2.1 - Windows audio (PyAudio ships PortAudio precompiled)"

# --- Step 2.2  Python venv ---------------------------------------------------
Write-Log "Step 2.2 - Creating Python venv at $VENV_DIR"

if ($PYTHON_BIN -eq "python3_missing" -or [string]::IsNullOrWhiteSpace($PYTHON_BIN)) {
    Write-Warn "Python 3.10+ not found -- skipping venv and pip installs"
    Write-Warn "Install Python from https://www.python.org/downloads/ then re-run setup.ps1"
    exit 1
}

Run-Or-Warn "create venv" { & $PYTHON_BIN -m venv $VENV_DIR }

Write-Log "Step 2.3 - Installing Python packages"
$VENV_PIP    = Join-Path $VENV_DIR "Scripts\pip.exe"
$VENV_PYTHON = Join-Path $VENV_DIR "Scripts\python.exe"

if (-not (Test-Path $VENV_PIP)) {
    Write-Warn "pip not found at $VENV_PIP -- venv creation may have failed"
} else {
    Run-Or-Warn "pip upgrade"         { & $VENV_PYTHON -m pip install --upgrade pip --quiet }
    Run-Or-Warn "install websockets"  { & $VENV_PIP install "websockets>=12.0" --quiet }
    Run-Or-Warn "install SpeechRecog" { & $VENV_PIP install "SpeechRecognition>=3.10.4" --quiet }
    Run-Or-Warn "install python-jose" { & $VENV_PIP install "python-jose[cryptography]>=3.3.0" --quiet }
    Run-Or-Warn "install pyttsx3"     { & $VENV_PIP install "pyttsx3>=2.90" --quiet }

    # PyAudio — official wheel first, pipwin fallback
    Write-Log "  Installing PyAudio..."
    $pyaudioOk = $false
    try {
        $out = & $VENV_PIP install "PyAudio>=0.2.14" --quiet 2>&1
        $out | ForEach-Object { Add-Content -Path $LOG_FILE -Value "$_" }
        if ($LASTEXITCODE -eq 0) { Write-Log "  OK: install PyAudio (official)"; $pyaudioOk = $true }
    } catch { }

    if (-not $pyaudioOk) {
        Write-Warn "Official PyAudio wheel failed -- trying pipwin fallback"
        try {
            & $VENV_PIP install pipwin --quiet 2>&1 | Out-Null
            & $VENV_PYTHON -m pipwin install pyaudio 2>&1 | ForEach-Object { Add-Content -Path $LOG_FILE -Value "$_" }
            if ($LASTEXITCODE -eq 0) { Write-Log "  OK: install PyAudio (via pipwin)"; $pyaudioOk = $true }
        } catch { }
    }

    if (-not $pyaudioOk) {
        Write-Warn "PyAudio install failed -- microphone capture disabled (voice bridge still runs)"
    }
}

# Write venv python path back to env.conf
$existing = Get-Content $CONF_FILE -Raw -ErrorAction SilentlyContinue
if ($existing -notmatch "VENV_PYTHON=") { Add-Content -Path $CONF_FILE -Value "VENV_PYTHON=$VENV_PYTHON" }
if ($existing -notmatch "REPO_ROOT=")   { Add-Content -Path $CONF_FILE -Value "REPO_ROOT=$RepoRoot" }

# --- Step 3  Service registration + immediate start --------------------------
Write-Log "Step 3 - Registering launch method (SVC_MGR=$SVC_MGR)"

$LogFile     = Join-Path $CONF_DIR "voice-bridge.log"
$TaskName    = "AgentiumVoiceBridge"
$startupDir  = [Environment]::GetFolderPath("Startup")

# ── Helper: kill any existing bridge process ─────────────────────────────────
function Stop-ExistingBridge {
    Get-WmiObject Win32_Process | Where-Object {
        $_.CommandLine -like "*voice-bridge*main.py*" -or
        $_.CommandLine -like "*agentium*main.py*"
    } | ForEach-Object {
        Write-Log "  Stopping existing bridge process (PID $($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# ── Helper: verify bridge started ────────────────────────────────────────────
function Test-BridgeStarted {
    Start-Sleep -Seconds 4
    $listening = netstat -ano 2>$null | Select-String ":9999"
    if ($listening) {
        Write-Log "  Bridge is listening on port 9999 ✓"
        return $true
    }
    Write-Warn "Port 9999 not yet listening -- check $LogFile"
    return $false
}

# =============================================================================
# PATH A: VBScript + Startup shortcut (Store Python / no UAC for task needed)
# =============================================================================
if ($SVC_MGR -eq "vbs_startup" -or $IS_STORE_PYTHON -eq "true") {
    Write-Log "  Using VBScript launcher (Store Python detected)"

    # Remove any old scheduled task to avoid confusion
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # Write VBScript that launches main.py hidden in the user session
    # WScript.Shell.Run with window=0 works perfectly with Store Python
    # because it inherits the interactive user session — no Store activation needed
    $vbsPath = Join-Path $CONF_DIR "start-voice-bridge.vbs"
    $vbs = @"
' Agentium Voice Bridge launcher — auto-generated by installer
' Uses WScript.Shell so Store Python runs in the interactive user session.
Dim sh, logFile, pidFile, fso
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pidFile = sh.ExpandEnvironmentStrings("%USERPROFILE%") & "\.agentium\voice-bridge.pid"
logFile = "$($LogFile -replace '\\','\\')"

' Kill old instance if pid file exists
If fso.FileExists(pidFile) Then
    On Error Resume Next
    Dim oldPid
    oldPid = fso.OpenTextFile(pidFile, 1).ReadAll()
    sh.Run "taskkill /F /PID " & Trim(oldPid), 0, True
    fso.DeleteFile pidFile
    On Error GoTo 0
End If

' Launch the bridge hidden (window style 0 = hidden)
Dim cmd
cmd = """$($VENV_PYTHON -replace '\\','\\')""" & " " & """$($MainPy -replace '\\','\\')"""
sh.Run cmd, 0, False
"@
    $vbs | Set-Content $vbsPath -Encoding ASCII
    Write-Log "  VBS launcher written: $vbsPath"

    # Write Startup folder shortcut (.lnk) so bridge auto-starts on every login
    $lnkPath = Join-Path $startupDir "AgentiumVoiceBridge.lnk"
    try {
        $wshell   = New-Object -ComObject WScript.Shell
        $shortcut = $wshell.CreateShortcut($lnkPath)
        $shortcut.TargetPath  = "wscript.exe"
        $shortcut.Arguments   = "`"$vbsPath`""
        $shortcut.WindowStyle = 7   # minimised
        $shortcut.Description = "Agentium Voice Bridge (auto-start)"
        $shortcut.Save()
        Write-Log "  Startup shortcut written: $lnkPath"
    } catch {
        Write-Warn "Could not write Startup shortcut: $_ -- bridge won't auto-start on login"
    }

    # Start RIGHT NOW
    Stop-ExistingBridge
    Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden
    Write-Log "  Bridge launched via wscript."
    Test-BridgeStarted | Out-Null

    Write-Log "  Auto-start: shortcut in $startupDir"
    Write-Log "  Manual start: wscript.exe `"$vbsPath`""
}

# =============================================================================
# PATH B: Windows Task Scheduler (real Python install)
# =============================================================================
elseif ($SVC_MGR -eq "task_scheduler") {
    Write-Log "  Using Task Scheduler (real Python install)"

    # Write launcher .bat
    $LauncherBat = Join-Path $CONF_DIR "start-voice-bridge.bat"
    @(
        "@echo off",
        ":: Auto-generated by Agentium installer",
        "set LOGFILE=$LogFile",
        "`"$VENV_PYTHON`" `"$MainPy`" >> `"%LOGFILE%`" 2>&1"
    ) | Set-Content -Path $LauncherBat -Encoding ASCII
    Write-Log "  Launcher bat written: $LauncherBat"

    # Remove old task
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $action    = New-ScheduledTaskAction -Execute $LauncherBat
    $trigger   = New-ScheduledTaskTrigger -AtLogon -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal `
        -UserId "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel Limited
    $settings  = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0)

    try {
        Register-ScheduledTask `
            -TaskName  $TaskName `
            -Action    $action `
            -Trigger   $trigger `
            -Principal $principal `
            -Settings  $settings `
            -Force | Out-Null

        Write-Log "  Scheduled task '$TaskName' registered"

        Stop-ExistingBridge
        Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        $state = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
        Write-Log "  Task state: $state"

        if ($state -ne "Running") {
            Write-Warn "Task not Running (state=$state) -- falling back to direct launch"
            Start-Process -FilePath $LauncherBat -WindowStyle Hidden -ErrorAction SilentlyContinue
        }

        Test-BridgeStarted | Out-Null

    } catch {
        Write-Warn "Scheduled task registration failed: $_ -- falling back to Startup folder"

        $startupBat = Join-Path $startupDir "agentium-voice-bridge.bat"
        Copy-Item $LauncherBat $startupBat -Force
        Write-Log "  Startup bat written: $startupBat"

        Stop-ExistingBridge
        Start-Process -FilePath $LauncherBat -WindowStyle Hidden -ErrorAction SilentlyContinue
        Test-BridgeStarted | Out-Null
    }
}

# =============================================================================
# PATH C: Unknown — best-effort direct launch
# =============================================================================
else {
    Write-Warn "Unknown SVC_MGR='$SVC_MGR' -- attempting direct launch"
    Stop-ExistingBridge
    $LauncherBat = Join-Path $CONF_DIR "start-voice-bridge.bat"
    @(
        "@echo off",
        "`"$VENV_PYTHON`" `"$MainPy`" >> `"$LogFile`" 2>&1"
    ) | Set-Content -Path $LauncherBat -Encoding ASCII
    Start-Process -FilePath $LauncherBat -WindowStyle Hidden -ErrorAction SilentlyContinue
    Test-BridgeStarted | Out-Null
}

Write-Log "=== Installation complete. Check $LOG_FILE for details. ==="