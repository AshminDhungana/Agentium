# scripts/uninstall-voice-bridge.ps1
# Stops and removes the Agentium voice bridge. Non-destructive to Docker stack.
# Automatically requests UAC elevation if needed.

$ErrorActionPreference = "Continue"

# --- Self-elevation ----------------------------------------------------------
function Test-IsAdmin {
    ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "Agentium uninstaller needs administrator access." -ForegroundColor Yellow
    Write-Host "A UAC prompt will appear -- please click Yes to continue." -ForegroundColor Yellow

    $scriptPath = $MyInvocation.MyCommand.Path
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName        = "powershell.exe"
    $psi.Arguments       = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
    $psi.Verb            = "runas"
    $psi.UseShellExecute = $true

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
        $proc.WaitForExit()
        exit $proc.ExitCode
    } catch {
        Write-Host "UAC elevation cancelled. Uninstall aborted." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
}

$CONF_DIR  = Join-Path $env:USERPROFILE ".agentium"
$TaskName  = "AgentiumVoiceBridge"

function Write-Log($msg) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $msg" }

Write-Log "=== Agentium Voice Bridge Uninstaller ==="

# --- Remove every autoinstall artifact (legacy + current) -------------------
$startupFolder = [Environment]::GetFolderPath("Startup")
$artifacts = @(
    (Join-Path $startupFolder "agentium-voice-startup.cmd")
    (Join-Path $startupFolder "agentium-voice-prompt.cmd")
    (Join-Path $startupFolder "agentium-voice-setup.hta")
    (Join-Path $startupFolder "agentium-voice-bridge.bat")
    (Join-Path $startupFolder "AgentiumVoiceBridge.lnk")
    (Join-Path $CONF_DIR     "bootstrap-voice.cmd")
    (Join-Path $CONF_DIR     "prompt.vbs")
    (Join-Path $CONF_DIR     "run-prompt.cmd")
    (Join-Path $CONF_DIR     "agentium-runonce.reg")
    (Join-Path $CONF_DIR     "voice-installed.marker")
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Install Agentium Voice Bridge.cmd")
)
foreach ($a in $artifacts) {
    if (Test-Path $a) {
        Remove-Item $a -Force -ErrorAction SilentlyContinue
        Write-Log "Removed: $a"
    }
}

# --- Stop and remove scheduled task ------------------------------------------
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.State -eq "Running") {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Log "Task stopped."
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Log "Scheduled task '$TaskName' removed."
} else {
    Write-Log "Scheduled task '$TaskName' not found -- skipping."
}

Write-Log "Venv and conf files left in $CONF_DIR (remove manually if desired)"
Write-Log "=== Uninstall complete ==="

if ($Host.Name -eq "ConsoleHost") {
    Read-Host "Press Enter to close"
}