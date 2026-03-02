# scripts/detect-host.ps1 - Agentium OS probe for Windows
# Writes $env:USERPROFILE\.agentium\env.conf
# Usage: detect-host.ps1 [-RepoRoot <path>]

param(
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Continue"

$CONF_DIR  = Join-Path $env:USERPROFILE ".agentium"
$CONF_FILE = Join-Path $CONF_DIR "env.conf"
$LOG_FILE  = Join-Path $CONF_DIR "detect.log"

New-Item -ItemType Directory -Force -Path $CONF_DIR | Out-Null
"" | Set-Content $CONF_FILE
"" | Set-Content $LOG_FILE

$WARN_COUNT = 0

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
    $script:WARN_COUNT++
}

function Write-Conf($key, $val) {
    Add-Content -Path $CONF_FILE -Value "$key=$val"
}

Write-Log "=== Agentium OS Detection Started ==="

# Step 1.1 - OS family
Write-Log "Step 1.1 - Detecting OS family"
Write-Conf "OS_FAMILY" "windows"
Write-Log "  OS_FAMILY=windows"

# Step 1.2 - Windows version
Write-Log "Step 1.2 - Detecting Windows version"
try {
    $WIN_VERSION = (Get-CimInstance Win32_OperatingSystem).Caption
} catch {
    $WIN_VERSION = "Windows (unknown)"
}
Write-Conf "WIN_VERSION" $WIN_VERSION
Write-Log "  WIN_VERSION=$WIN_VERSION"

# Step 1.3 - Package manager
Write-Log "Step 1.3 - Selecting package manager"
$PKG_MGR = "pip"
if (Get-Command winget -ErrorAction SilentlyContinue) {
    $PKG_MGR = "winget"
} elseif (Get-Command choco -ErrorAction SilentlyContinue) {
    $PKG_MGR = "choco"
}
Write-Conf "PKG_MGR" $PKG_MGR
Write-Log "  PKG_MGR=$PKG_MGR"

# Step 1.4 - Python (real executable, Store stub detection)
Write-Log "Step 1.4 - Locating Python 3.10 or newer"

$PYTHON_BIN     = $null
$IS_STORE_PYTHON = "false"

# Helper: test if a path is the Windows Store stub
function Test-IsStorePython($path) {
    if (-not $path) { return $false }
    # Store stubs live under WindowsApps or contain the Store package name
    if ($path -like "*WindowsApps*")               { return $true }
    if ($path -like "*PythonSoftwareFoundation*")   { return $true }
    return $false
}

# Helper: verify a python binary is >= 3.10 and actually executable
function Test-PythonOk($bin) {
    if (-not $bin -or -not (Test-Path $bin -ErrorAction SilentlyContinue)) { return $false }
    try {
        $ver = & $bin -c "import sys; print(sys.version_info >= (3,10))" 2>$null
        return ($ver -eq "True")
    } catch { return $false }
}

# Candidate list — real install locations first, Store stub last
$candidates = @(
    # Explicit version-named commands (real installs usually register these)
    "python3.13","python3.12","python3.11","python3.10",
    # Generic names
    "python3","python"
)

# First pass: prefer non-Store Python
foreach ($candidate in $candidates) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $exePath = $cmd.Source

    # Resolve the real executable path (handles aliases/shims)
    try {
        $resolved = & $exePath -c "import sys; print(sys.executable)" 2>$null
        if ($resolved -and (Test-Path $resolved)) { $exePath = $resolved }
    } catch {}

    if (Test-IsStorePython $exePath) { continue }   # skip Store stubs in first pass
    if (Test-PythonOk $exePath) {
        $PYTHON_BIN = $exePath
        break
    }
}

# Second pass: also check common real-install directories directly
if (-not $PYTHON_BIN) {
    $directPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Python313\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )
    foreach ($p in $directPaths) {
        if (Test-PythonOk $p) {
            $PYTHON_BIN = $p
            break
        }
    }
}

# Third pass: fall back to Store Python if nothing else found
if (-not $PYTHON_BIN) {
    foreach ($candidate in $candidates) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $exePath = $cmd.Source
        try {
            $resolved = & $exePath -c "import sys; print(sys.executable)" 2>$null
            if ($resolved -and (Test-Path $resolved)) { $exePath = $resolved }
        } catch {}
        if (Test-PythonOk $exePath) {
            $PYTHON_BIN     = $exePath
            $IS_STORE_PYTHON = "true"
            Write-Warn "Only Windows Store Python found — will use VBScript launcher instead of scheduled task"
            break
        }
    }
}

if (-not $PYTHON_BIN) {
    Write-Warn "No Python 3.10+ found — voice bridge venv will not be created"
    Write-Warn "Install Python from https://www.python.org/downloads/ then re-run setup.ps1"
    Write-Conf "PYTHON_BIN" "python3_missing"
    Write-Conf "IS_STORE_PYTHON" "false"
} else {
    $verStr = & $PYTHON_BIN --version 2>&1
    Write-Conf "PYTHON_BIN" $PYTHON_BIN
    Write-Conf "IS_STORE_PYTHON" $IS_STORE_PYTHON
    Write-Log "  PYTHON_BIN=$PYTHON_BIN ($verStr)"
    Write-Log "  IS_STORE_PYTHON=$IS_STORE_PYTHON"
}

# Step 1.5 - Microphone
Write-Log "Step 1.5 - Microphone (runtime detection via PyAudio)"
Write-Conf "HAS_MIC" "true"
Write-Log "  HAS_MIC=true"

# Step 1.6 - Docker / backend URL
Write-Log "Step 1.6 - Detecting backend URL"
$BACKEND_URL = "http://127.0.0.1:8000"
$urlsToTry = @("http://127.0.0.1:8000", "http://localhost:8000", "http://host.docker.internal:8000")
foreach ($url in $urlsToTry) {
    try {
        $resp = Invoke-WebRequest -Uri "$url/api/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $BACKEND_URL = $url
            Write-Log "  Backend reachable at $url"
            break
        }
    } catch { }
}
Write-Conf "BACKEND_URL" $BACKEND_URL
Write-Log "  BACKEND_URL=$BACKEND_URL"

# Step 1.7 - Service manager
# If Store Python detected, override to vbs_startup so installer knows to use VBScript method
Write-Log "Step 1.7 - Detecting service manager"
if ($IS_STORE_PYTHON -eq "true") {
    Write-Conf "SVC_MGR" "vbs_startup"
    Write-Log "  SVC_MGR=vbs_startup (Store Python detected — scheduled task won't work)"
} else {
    Write-Conf "SVC_MGR" "task_scheduler"
    Write-Log "  SVC_MGR=task_scheduler"
}

# Step 1.8 - WS port and wake word
Write-Conf "WS_PORT"   "9999"
Write-Conf "WAKE_WORD" "agentium"

# Write REPO_ROOT
if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
    Write-Conf "REPO_ROOT" $RepoRoot
    Write-Log "  REPO_ROOT=$RepoRoot"
}

Write-Log "=== Detection complete - $WARN_COUNT warning(s) - written to $CONF_FILE ==="