# setup.ps1 - Windows entry point for Agentium Voice Bridge
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Automatically requests UAC elevation if needed.
# NOTE: param() MUST be the first executable statement — only comments above it.
param(
    [string]$RepoRoot = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Resolve repo root from PSScriptRoot when not passed in
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "Agentium needs administrator access to register the startup task." -ForegroundColor Yellow
    Write-Host "A UAC prompt will appear -- please click Yes to continue." -ForegroundColor Yellow
    Write-Host ""

    $scriptPath = $MyInvocation.MyCommand.Path

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = "powershell.exe"
    $psi.Arguments       = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -RepoRoot `"$RepoRoot`""
    $psi.Verb            = "runas"
    $psi.UseShellExecute = $true

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $proc.WaitForExit()
        exit $proc.ExitCode
    } catch {
        Write-Host ""
        Write-Host "UAC elevation was cancelled or denied." -ForegroundColor Red
        Write-Host "To install manually, right-click PowerShell, choose 'Run as Administrator', then run:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptPath`"" -ForegroundColor Cyan
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Already installed? Skip the full (UAC-triggering) reinstall unless forced.
# ---------------------------------------------------------------------------
$Marker = Join-Path $env:USERPROFILE ".agentium\voice-installed.marker"
if ((Test-Path $Marker) -and -not $Force) {
    Write-Host "Agentium voice bridge is already installed." -ForegroundColor Green
    Write-Host "Run with -Force to reinstall." -ForegroundColor Yellow
    exit 0
}

# ---------------------------------------------------------------------------
# Now running as Administrator
# ---------------------------------------------------------------------------

Write-Host "=== Agentium Voice Bridge Windows Installer ===" -ForegroundColor Cyan
Write-Host "Running as Administrator: YES"                   -ForegroundColor Green
Write-Host "Repo root: $RepoRoot"
Write-Host ""

# Validate repo root contains the expected files
$MainPy = Join-Path $RepoRoot "voice-bridge\main.py"
if (-not (Test-Path $MainPy)) {
    Write-Host "[setup.ps1] ERROR: voice-bridge\main.py not found under $RepoRoot" -ForegroundColor Red
    Write-Host "  Check that REPO_ROOT is correct and re-run this script." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Phase 1: OS detection
Write-Host "[setup.ps1] Running OS detection..." -ForegroundColor Yellow
$detectScript = Join-Path $RepoRoot "scripts\detect-host.ps1"
if (-not (Test-Path $detectScript)) {
    Write-Host "[setup.ps1] ERROR: detect-host.ps1 not found at $detectScript" -ForegroundColor Red
    exit 1
}
& $detectScript -RepoRoot $RepoRoot
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    Write-Host "[setup.ps1] WARN: detect-host.ps1 exited $LASTEXITCODE -- continuing" -ForegroundColor Yellow
}

# Phase 2+3: deps + service registration
Write-Host "[setup.ps1] Running dependency installer..." -ForegroundColor Yellow
$installScript = Join-Path $RepoRoot "scripts\install-voice-bridge.ps1"
if (-not (Test-Path $installScript)) {
    Write-Host "[setup.ps1] ERROR: install-voice-bridge.ps1 not found at $installScript" -ForegroundColor Red
    exit 1
}
& $installScript -RepoRoot $RepoRoot
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    Write-Host "[setup.ps1] WARN: install-voice-bridge.ps1 exited $LASTEXITCODE -- check install.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Voice bridge installation complete ===" -ForegroundColor Green
Write-Host "Log: $env:USERPROFILE\.agentium\install.log"
Write-Host ""

# ---------------------------------------------------------------------------
# Verify the bridge is actually listening on port 9999
# ---------------------------------------------------------------------------
Write-Host "[setup.ps1] Verifying bridge is listening on port 9999..." -ForegroundColor Yellow

$maxWait  = 15   # seconds
$interval = 2
$elapsed  = 0
$bridgeUp = $false

while ($elapsed -le $maxWait) {
    # netstat check
    $portLine = netstat -ano 2>$null | Select-String ":9999\s"
    if ($portLine) {
        $bridgeUp = $true
        break
    }

    # Also try a direct TCP connect as a more reliable alternative
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 9999)
        $tcp.Close()
        $bridgeUp = $true
        break
    } catch { }

    Start-Sleep -Seconds $interval
    $elapsed += $interval
    Write-Host "  Waiting for bridge... ($elapsed`s)" -ForegroundColor DarkGray
}

if ($bridgeUp) {
    Write-Host "  Bridge is UP and listening on port 9999 [OK]" -ForegroundColor Green
} else {
    Write-Host "  Bridge did NOT start within $maxWait`s -- check log below" -ForegroundColor Red

    $logFile = "$env:USERPROFILE\.agentium\voice-bridge.log"
    if (Test-Path $logFile) {
        Write-Host ""
        Write-Host "--- Last 20 lines of voice-bridge.log ---" -ForegroundColor Yellow
        Get-Content $logFile -Tail 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "-----------------------------------------"
    }
}

# ---------------------------------------------------------------------------
# Useful commands
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  Check port  : netstat -ano | findstr :9999"
Write-Host "  View logs   : Get-Content `"$env:USERPROFILE\.agentium\voice-bridge.log`" -Tail 50"
Write-Host "  Task status : Get-ScheduledTask -TaskName AgentiumVoiceBridge -ErrorAction SilentlyContinue"
Write-Host "  Start task  : Start-ScheduledTask -TaskName AgentiumVoiceBridge"
Write-Host "  Kill bridge : Get-WmiObject Win32_Process | Where-Object { `$_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }"
Write-Host ""

if ($Host.Name -eq "ConsoleHost") {
    Read-Host "Press Enter to close"
}