# scripts/install-voice-bridge.ps1 - Agentium voice bridge installer (Windows)
# Reads $env:USERPROFILE\.agentium\env.conf written by detect-host.ps1
# Supports two launch strategies:
#   task_scheduler â€” real Python install, registers Windows Task Scheduler + starts immediately
#   vbs_startup    â€” Windows Store Python, uses VBScript + Startup folder shortcut
# NOTE: Called from setup.ps1 which already handles UAC elevation.

param(
    [string]$RepoRoot = "",
    [switch]$VbsOnly
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

# Resolve REPO_ROOT (parameter > env.conf > derive from script location)
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = $conf["REPO_ROOT"] }
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $candidate = Split-Path $PSScriptRoot -Parent
    if (Test-Path (Join-Path $candidate "voice-bridge\main.py")) { $RepoRoot = $candidate }
}

$BRIDGE_DIR = if ($RepoRoot) { Join-Path $RepoRoot "voice-bridge" } else { "" }
$MainPy     = if ($BRIDGE_DIR) { Join-Path $BRIDGE_DIR "main.py" } else { "" }
$BridgeLog  = Join-Path $CONF_DIR "voice-bridge.log"
$PidFile    = Join-Path $CONF_DIR "voice-bridge.pid"
$TaskName   = "AgentiumVoiceBridge"
$StartupDir = [Environment]::GetFolderPath("Startup")

# Tracks whether the bridge actually came up; gates the install marker so a
# failed start does not mark the install "done" and disable re-prompting.
$BridgeUp = $false

# --- Remove legacy / duplicate trigger artifacts so we never double-start ----
function Remove-IfExists($path) {
    if (Test-Path $path) {
        Remove-Item $path -Force -ErrorAction SilentlyContinue
        Write-Log "  Removed legacy artifact: $path"
    }
}
Remove-IfExists (Join-Path $StartupDir "agentium-voice-prompt.cmd")
Remove-IfExists (Join-Path $StartupDir "agentium-voice-setup.hta")
Remove-IfExists (Join-Path $CONF_DIR   "prompt.vbs")
Remove-IfExists (Join-Path $CONF_DIR   "run-prompt.cmd")
Remove-IfExists (Join-Path $CONF_DIR   "agentium-runonce.reg")
Remove-IfExists (Join-Path $StartupDir "AgentiumVoiceBridge.lnk")

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

# =============================================================================
# Step 2.1  System audio (PyAudio ships PortAudio pre-compiled on Windows)
# =============================================================================
Write-Log "Step 2.1 - Windows audio (PyAudio ships PortAudio precompiled)"

# =============================================================================
# Step 2.2  Python venv
# =============================================================================
Write-Log "Step 2.2 - Creating Python venv at $VENV_DIR"

if ($PYTHON_BIN -eq "python3_missing" -or [string]::IsNullOrWhiteSpace($PYTHON_BIN)) {
    Write-Warn "Python 3.10+ not found -- skipping venv and pip installs"
    Write-Warn "Install Python from https://www.python.org/downloads/ then re-run setup.ps1"
    Write-Warn "Continuing without voice bridge installation..."
    # Don't exit - let setup.ps1 continue to show the error and wait for input
} else {
    Run-Or-Warn "create venv" { & $PYTHON_BIN -m venv $VENV_DIR }
}

# =============================================================================
# Step 2.3  Python packages
# =============================================================================
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
    Run-Or-Warn "install numpy"       { & $VENV_PIP install "numpy>=1.24" --quiet }

    # PyAudio â€” official wheel first, pipwin fallback
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
        Write-Warn "PyAudio install failed -- microphone capture disabled (voice bridge still runs without it)"
    }
}

# Persist venv python path and repo root to env.conf so main.py can read them
$existing = Get-Content $CONF_FILE -Raw -ErrorAction SilentlyContinue
if ($existing -notmatch "VENV_PYTHON=") { Add-Content -Path $CONF_FILE -Value "VENV_PYTHON=$VENV_PYTHON" }
if ($existing -notmatch "REPO_ROOT=")   { Add-Content -Path $CONF_FILE -Value "REPO_ROOT=$RepoRoot" }

# =============================================================================
# Shared helpers
# =============================================================================

# Kill any existing bridge process (by command-line pattern)
function Stop-ExistingBridge {
    Get-WmiObject Win32_Process 2>$null | Where-Object {
        $_.CommandLine -like "*voice-bridge*main.py*" -or
        $_.CommandLine -like "*agentium*main.py*"
    } | ForEach-Object {
        Write-Log "  Stopping existing bridge process (PID $($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    # Also clean up stale pid file
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 500
}

# Poll port 9999 until the bridge is listening or timeout
function Wait-ForBridge {
    param([int]$TimeoutSeconds = 20)
    $elapsed = 0
    $interval = 2
    while ($elapsed -le $TimeoutSeconds) {
        # Try netstat first
        $portLine = netstat -ano 2>$null | Select-String ":9999\s"
        if ($portLine) { return $true }

        # Try direct TCP connect
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", 9999)
            $tcp.Close()
            return $true
        } catch { }

        if ($elapsed -eq 0) {
            Write-Log "  Waiting for bridge to start on port 9999..."
        }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
    }
    return $false
}

# Direct Start-Process launch â€” used as primary start AND as fallback
# This is the ONLY method guaranteed to work immediately in all situations.
function Start-BridgeDirect {
    param([string]$Label = "direct")

    Stop-ExistingBridge

    if (-not (Test-Path $VENV_PYTHON)) {
        Write-Warn "VENV_PYTHON not found at $VENV_PYTHON -- cannot start bridge"
        return $false
    }
    if (-not (Test-Path $MainPy)) {
        Write-Warn "main.py not found at $MainPy -- cannot start bridge"
        return $false
    }

    Write-Log "  Launching bridge ($Label): $VENV_PYTHON $MainPy"

    # Launch via cmd.exe /c so both stdout and stderr go to a single log file.
    # PowerShell's Start-Process does not allow -RedirectStandardOutput and
    # -RedirectStandardError to point to the same path (error in PS 7+), so
    # we use cmd.exe redirection instead — this is reliable on all versions.
    try {
        $cmdArgs = "/c `"`"$VENV_PYTHON`" `"$MainPy`" >> `"$BridgeLog`" 2>&1`""
        $proc = Start-Process `
            -FilePath       "cmd.exe" `
            -ArgumentList   $cmdArgs `
            -WindowStyle    Hidden `
            -PassThru `
            -ErrorAction    Stop

        $proc.Id | Set-Content $PidFile
        Write-Log "  Bridge process started (PID $($proc.Id))"
        return $true
    } catch {
        Write-Warn "Direct start failed: $_ -- trying cmd /c start fallback"
        try {
            $cmdArgs = "/c start /min `"`" `"$VENV_PYTHON`" `"$MainPy`" >> `"$BridgeLog`" 2>&1"
            Start-Process "cmd.exe" -ArgumentList $cmdArgs -WindowStyle Hidden -ErrorAction Stop
            Write-Log "  Bridge started via cmd start fallback"
            return $true
        } catch {
            Write-Warn "cmd start fallback also failed: $_"
            return $false
        }
    }
    }
}

# =============================================================================
# Step 3  Service registration + IMMEDIATE start
# =============================================================================
Write-Log "Step 3 - Registering launch method (SVC_MGR=$SVC_MGR)"

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATH A: VBScript + Startup shortcut (no admin needed)
# Used for: Store Python OR when -VbsOnly is passed
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if ($SVC_MGR -eq "vbs_startup" -or $IS_STORE_PYTHON -eq "true" -or $VbsOnly) {
    if ($VbsOnly) {
        Write-Log "  Using VBScript launcher (VbsOnly mode - no admin required)"
    }
    Write-Log "  Using VBScript launcher (Store Python detected)"

    # Remove any old scheduled task
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # Write VBScript that launches main.py hidden in the interactive user session.
    # wscript.exe Run with window=0 inherits the user session -- no Store activation
    # or AppContainer sandbox issue.
    $vbsPath = Join-Path $CONF_DIR "start-voice-bridge.vbs"

    # Escape backslashes for embedding in the VBS string literals
    $venvPyEsc = $VENV_PYTHON -replace '\\', '\\'
    $mainPyEsc = $MainPy      -replace '\\', '\\'
    $logEsc    = $BridgeLog   -replace '\\', '\\'
    $pidEsc    = $PidFile     -replace '\\', '\\'

    $vbs = @"
' Agentium Voice Bridge launcher -- auto-generated by installer
' Uses WScript.Shell so Store Python runs in the interactive user session.
Dim sh, fso
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

Dim pidFile : pidFile = "$pidEsc"
Dim logFile : logFile = "$logEsc"

' Kill old instance if pid file exists and process is still running
If fso.FileExists(pidFile) Then
    On Error Resume Next
    Dim oldPid
    oldPid = Trim(fso.OpenTextFile(pidFile, 1).ReadAll())
    If oldPid <> "" Then
        sh.Run "taskkill /F /PID " & oldPid, 0, True
    End If
    fso.DeleteFile pidFile
    On Error GoTo 0
End If

' Launch the bridge hidden (window style 0 = hidden, bWaitOnReturn = False)
Dim cmd
cmd = Chr(34) & "$venvPyEsc" & Chr(34) & " " & Chr(34) & "$mainPyEsc" & Chr(34)
sh.Run cmd, 0, False

' Give the process a moment to appear, then record its PID
WScript.Sleep 2000
Dim oWMI, oProcs, oProc
Set oWMI   = GetObject("winmgmts:\\.\root\cimv2")
Set oProcs = oWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe'")
For Each oProc In oProcs
    If InStr(oProc.CommandLine, "main.py") > 0 Then
        Dim f : Set f = fso.OpenTextFile(pidFile, 2, True)
        f.Write CStr(oProc.ProcessId)
        f.Close
        Exit For
    End If
Next
"@
    $vbs | Set-Content $vbsPath -Encoding ASCII
    Write-Log "  VBS launcher written: $vbsPath"

    # Write Startup shortcut so bridge auto-starts on every login
    $lnkPath = Join-Path $StartupDir "AgentiumVoiceBridge.lnk"
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

    # â”€â”€ Start RIGHT NOW â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Prefer Start-BridgeDirect (reliable) -- VBScript path as secondary.
    $started = Start-BridgeDirect -Label "Store-Python/direct"
    if (-not $started) {
        Write-Log "  Falling back to wscript launcher..."
        Stop-ExistingBridge
        Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden
    }

    $up = Wait-ForBridge -TimeoutSeconds 20
    $BridgeUp = $up
    if ($up) {
        Write-Log "  Bridge is UP on port 9999 [OK]"
    } else {
        Write-Warn "Bridge did NOT come up within 20s -- check $BridgeLog"
    }

    Write-Log "  Auto-start: shortcut in $StartupDir"
    Write-Log "  Manual start: wscript.exe `"$vbsPath`""
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATH B: Task Scheduler (real Python install)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
elseif ($SVC_MGR -eq "task_scheduler") {
    Write-Log "  Using Task Scheduler (real Python install)"

    # Write a minimal launcher .bat.
    # IMPORTANT: do NOT redirect stdout/stderr to a file here with >>
    # because that causes cmd.exe to keep the file handle open and the
    # Python process can block waiting to write. Let main.py own its own
    # log file (it uses logging.StreamHandler). We redirect only at the
    # Start-Process level or let the scheduler capture it.
    $LauncherBat = Join-Path $CONF_DIR "start-voice-bridge.bat"
    @(
        "@echo off",
        ":: Auto-generated by Agentium installer -- do not edit",
        "`"$VENV_PYTHON`" `"$MainPy`""
    ) | Set-Content -Path $LauncherBat -Encoding ASCII
    Write-Log "  Launcher bat written: $LauncherBat"

    # Register the scheduled task (AtLogon, Interactive, no time limit)
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $action    = New-ScheduledTaskAction -Execute "`"$VENV_PYTHON`"" -Argument "`"$MainPy`""
    $trigger   = New-ScheduledTaskTrigger -AtLogon -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal `
        -UserId    "$env:USERDOMAIN\$env:USERNAME" `
        -LogonType Interactive `
        -RunLevel  Limited
    $settings  = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # no time limit

    $taskRegistered = $false
    try {
        Register-ScheduledTask `
            -TaskName  $TaskName `
            -Action    $action `
            -Trigger   $trigger `
            -Principal $principal `
            -Settings  $settings `
            -Force | Out-Null
        Write-Log "  Scheduled task '$TaskName' registered (runs at every logon)"
        $taskRegistered = $true
    } catch {
        Write-Warn "Scheduled task registration failed: $_ -- will use Startup folder as persistence fallback"

        # Persist via Startup folder as fallback
        $startupBat = Join-Path $StartupDir "agentium-voice-bridge.bat"
        Copy-Item $LauncherBat $startupBat -Force -ErrorAction SilentlyContinue
        Write-Log "  Startup bat written: $startupBat"
    }

    # â”€â”€ Start RIGHT NOW via Start-Process (most reliable) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Do NOT rely on Start-ScheduledTask here -- on many systems the task enters
    # "Ready" but the process never actually starts because there is no
    # interactive logon session available to the scheduler at that moment.
    # Start-Process always works because we ARE in an interactive session.
    $started = Start-BridgeDirect -Label "task_scheduler/direct"

    if (-not $started -and $taskRegistered) {
        # Secondary attempt via scheduler
        Write-Log "  Direct launch failed -- trying Start-ScheduledTask as fallback"
        try {
            Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            Write-Log "  Scheduled task triggered"
        } catch {
            Write-Warn "Start-ScheduledTask failed: $_"
        }
    }

    $up = Wait-ForBridge -TimeoutSeconds 20
    $BridgeUp = $up
    if ($up) {
        Write-Log "  Bridge is UP on port 9999 [OK]"
    } else {
        Write-Warn "Bridge did NOT come up within 20s"

        # Last resort: try running python directly (no bat wrapper)
        Write-Log "  Last-resort: launching python directly without bat wrapper..."
        Start-BridgeDirect -Label "last-resort" | Out-Null
        $up = Wait-ForBridge -TimeoutSeconds 15
        $BridgeUp = $up
        if ($up) {
            Write-Log "  Bridge is UP after last-resort launch [OK]"
        } else {
            Write-Warn "Bridge still not up -- check $BridgeLog"
            if (Test-Path $BridgeLog) {
                Write-Log "--- Last 20 lines of voice-bridge.log ---"
                Get-Content $BridgeLog -Tail 20 | ForEach-Object { Write-Log "  $_" }
            }
        }
    }
}

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PATH C: Unknown SVC_MGR -- best-effort direct launch only
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
else {
    Write-Warn "Unknown SVC_MGR='$SVC_MGR' -- attempting direct launch (no persistence)"

    $started = Start-BridgeDirect -Label "unknown-svc-mgr"
    $up = Wait-ForBridge -TimeoutSeconds 15
    if ($up) {
        Write-Log "  Bridge is UP on port 9999 [OK]"
    } else {
        Write-Warn "Bridge not up within 15s -- check $BridgeLog"
    }

    # Write Startup bat so at least it starts on next login
    $startupBat = Join-Path $StartupDir "agentium-voice-bridge.bat"
    @(
        "@echo off",
        "`"$VENV_PYTHON`" `"$MainPy`""
    ) | Set-Content -Path $startupBat -Encoding ASCII
    Write-Log "  Startup bat written for persistence: $startupBat"
}

# --- Signal successful install ONLY when the bridge is actually listening ---
# (so a failed start does not mark "done" and silently disable re-prompting)
$MarkerFile = Join-Path $CONF_DIR "voice-installed.marker"
if ($BridgeUp) {
    try {
        New-Item -Path $MarkerFile -ItemType File -Force -ErrorAction Stop | Out-Null
        Write-Log "  Install marker written: $MarkerFile"
    } catch {
        Write-Warn "Could not write install marker: $_"
    }
} else {
    Write-Warn "Bridge did NOT come up -- NOT writing install marker; will retry on next login."
}

Write-Log "=== Installation complete. Check $LOG_FILE for details. ==="