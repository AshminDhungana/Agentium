# setup.ps1 - Windows entry point for Agentium Voice Bridge
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
param(
    [string]$RepoRoot = "",
    [switch]$Force,
    [switch]$UseTaskScheduler
)

$ErrorActionPreference = "Continue"

function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Log file
$LogDir = Join-Path $env:USERPROFILE ".agentium"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "install.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$ts] === Agentium Voice Bridge Installer ===" | Set-Content $LogFile
"[$ts] RepoRoot = $RepoRoot" | Add-Content $LogFile
"[$ts] IsAdmin  = $(Test-IsAdmin)" | Add-Content $LogFile

function Write-Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# Resolve repo root from PSScriptRoot when not passed in
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

$isAdmin = Test-IsAdmin
$needsElevation = $UseTaskScheduler

# Admin elevation path (only when -UseTaskScheduler is explicitly passed)
if ($needsElevation -and -not $isAdmin) {
    Write-Log "Requesting UAC elevation (needed for Task Scheduler)..."
    Write-Host ""
    Write-Host "Agentium needs administrator access to register the scheduled task." -ForegroundColor Yellow
    Write-Host "A UAC prompt will appear -- please click Yes to continue." -ForegroundColor Yellow
    Write-Host ""

    $scriptPath = $MyInvocation.MyCommand.Path

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = "powershell.exe"
    $psi.Arguments       = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$scriptPath`" -RepoRoot `"$RepoRoot`" -UseTaskScheduler"
    $psi.Verb            = "runas"
    $psi.UseShellExecute = $true

    try {
        Write-Log "Starting elevated process..."
        $proc = [System.Diagnostics.Process]::Start($psi)
        Write-Log "Elevated process started (PID $($proc.Id))"
        Write-Host ""
        Write-Host "An administrator PowerShell window has opened." -ForegroundColor Cyan
        Write-Host "The installation log is also saved to:" -ForegroundColor Cyan
        Write-Host "  $LogFile" -ForegroundColor White
        Write-Host ""
        Write-Host "Once it finishes, close the admin window and run setup.ps1 again" -ForegroundColor Yellow
        Write-Host "WITHOUT -UseTaskScheduler for day-to-day use." -ForegroundColor Yellow
        Write-Host ""
        $proc.WaitForExit()
        exit $proc.ExitCode
    } catch {
        Write-Log "UAC elevation was cancelled or denied: $_"
        Write-Host ""
        Write-Host "UAC elevation was cancelled or denied." -ForegroundColor Red
        Write-Host ""
        Write-Host "To install as admin manually, right-click PowerShell, choose 'Run as Administrator', then run:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptPath`" -UseTaskScheduler" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Or run WITHOUT admin (recommended for first install):" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptPath`"" -ForegroundColor Cyan
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 1
    }
}

Write-Log "=== Agentium Voice Bridge Windows Installer ==="

# Already installed? Skip reinstall unless forced.
$Marker = Join-Path $env:USERPROFILE ".agentium\voice-installed.marker"
if ((Test-Path $Marker) -and -not $Force) {
    Write-Log "Already installed. (Use -Force to reinstall)"
    Write-Host ""
    Write-Host "Agentium voice bridge is already installed." -ForegroundColor Green
    Write-Host "Run with -Force to reinstall." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 0
}

Write-Log "Running as Administrator: $isAdmin"
Write-Log "UseTaskScheduler: $UseTaskScheduler"

# Validate repo root
$MainPy = Join-Path $RepoRoot "voice-bridge\main.py"
if (-not (Test-Path $MainPy)) {
    Write-Log "ERROR: voice-bridge\main.py not found under $RepoRoot"
    Write-Host ""
    Write-Host "[setup.ps1] ERROR: voice-bridge\main.py not found under $RepoRoot" -ForegroundColor Red
    Write-Host "  Check repo root: $RepoRoot" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Phase 1: OS detection
Write-Log "Phase 1: OS detection..."
$detectScript = Join-Path $RepoRoot "scripts\detect-host.ps1"
if (-not (Test-Path $detectScript)) {
    Write-Log "ERROR: detect-host.ps1 not found"
    Read-Host "Press Enter to exit"
    exit 1
}
& $detectScript -RepoRoot $RepoRoot
Write-Log "detect-host.ps1 exit code: $LASTEXITCODE"

# Phase 2+3: deps + service registration
Write-Log "Phase 2+3: Installing dependencies and bridge..."
$installScript = Join-Path $RepoRoot "scripts\install-voice-bridge.ps1"
if (-not (Test-Path $installScript)) {
    Write-Log "ERROR: install-voice-bridge.ps1 not found"
    Read-Host "Press Enter to exit"
    exit 1
}

if ($needsElevation -or $isAdmin) {
    & $installScript -RepoRoot $RepoRoot
} else {
    Write-Log "Non-admin mode: using VBS/Startup folder method (no Task Scheduler)"
    & $installScript -RepoRoot $RepoRoot -VbsOnly
}
Write-Log "install-voice-bridge.ps1 exit code: $LASTEXITCODE"

# Verify the bridge is listening on port 9999
Write-Log "Verifying bridge on port 9999..."

$maxWait  = 15
$interval = 2
$elapsed  = 0
$bridgeUp = $false

while ($elapsed -le $maxWait) {
    $portLine = netstat -ano 2>$null | Select-String ":9999\s"
    if ($portLine) {
        $bridgeUp = $true
        break
    }
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 9999)
        $tcp.Close()
        $bridgeUp = $true
        break
    } catch { }

    Start-Sleep -Seconds $interval
    $elapsed += $interval
    Write-Log "  Waiting for bridge... ($elapsed seconds)"
}

if ($bridgeUp) {
    Write-Log "Bridge is UP on port 9999 [OK]"
    Write-Host ""
    Write-Host "  Voice bridge is running!" -ForegroundColor Green
    Write-Host "  The browser should connect automatically. If not, refresh the page." -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Log "Bridge did NOT start within $maxWait seconds"
    Write-Host ""
    Write-Host "  Bridge did NOT start within $maxWait seconds" -ForegroundColor Red

    $bridgeLog = "$env:USERPROFILE\.agentium\voice-bridge.log"
    if (Test-Path $bridgeLog) {
        Write-Host ""
        Write-Host "--- Last 20 lines of $bridgeLog ---" -ForegroundColor Yellow
        Get-Content $bridgeLog -Tail 20 | ForEach-Object { Write-Host "  $_" }
        Write-Host "--------------------------------------"
    }
    Write-Host ""
    Write-Host "  Check install log: $LogFile" -ForegroundColor Cyan
}

# Summary
Write-Log "=== Installer finished ==="
Write-Host ""
Write-Host "=== Voice bridge setup complete ===" -ForegroundColor Green
Write-Host "  Log file: $LogFile" -ForegroundColor Cyan
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  Check port  : netstat -ano | findstr :9999"
Write-Host "  View logs   : Get-Content `"$env:USERPROFILE\.agentium\voice-bridge.log`" -Tail 50"
Write-Host "  Kill bridge : Get-WmiObject Win32_Process | Where-Object { `$_.CommandLine -like '*main.py*' } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }"
Write-Host ""
Read-Host "Press Enter to close"
