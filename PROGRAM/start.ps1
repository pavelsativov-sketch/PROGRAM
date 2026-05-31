# Floral AI - single-command launcher
# Usage: double-click start.bat, or: .\start.ps1
# Flags:
#   -NoWA     do not start WhatsApp bridge
#   -Install  force reinstall dependencies
#   -Stop     stop all running services
param(
  [switch]$NoWA,
  [switch]$Install,
  [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$logDir = Join-Path $root 'logs'
$pidFile = Join-Path $root '.pids.json'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Section($t) {
  Write-Host ""
  Write-Host "=== $t ===" -ForegroundColor Magenta
}

function Stop-All {
  if (-not (Test-Path $pidFile)) { Write-Host "No active services."; return }
  $pids = Get-Content $pidFile | ConvertFrom-Json
  foreach ($p in $pids.PSObject.Properties) {
    try {
      $proc = Get-Process -Id $p.Value -ErrorAction SilentlyContinue
      if ($proc) {
        Write-Host ("Stopping {0} (PID {1})..." -f $p.Name, $p.Value) -ForegroundColor Yellow
        Stop-Process -Id $p.Value -Force -ErrorAction SilentlyContinue
      }
    } catch {}
  }
  Remove-Item $pidFile -ErrorAction SilentlyContinue
  Write-Host "Stopped." -ForegroundColor Green
}

if ($Stop) { Stop-All; return }

if (Test-Path $pidFile) {
  Write-Host "Previous processes detected - stopping..." -ForegroundColor Yellow
  Stop-All
}

function Need-Cmd($cmd, $hint) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host ("[X] Not found: {0}" -f $cmd) -ForegroundColor Red
    Write-Host ("    {0}" -f $hint) -ForegroundColor Yellow
    exit 1
  }
}
Need-Cmd python "Install Python 3.10+ from https://www.python.org/downloads/"
Need-Cmd node   "Install Node.js 18+ from https://nodejs.org/"
Need-Cmd npm    "Usually comes with Node.js"

Write-Section "Backend (FastAPI)"
$backend = Join-Path $root 'backend'
$venv = Join-Path $backend '.venv'
if (-not (Test-Path $venv) -or $Install) {
  Write-Host "Creating virtual environment..."
  python -m venv $venv
}
$venvPy = Join-Path $venv 'Scripts\python.exe'
$venvPip = Join-Path $venv 'Scripts\pip.exe'

$markerFile = Join-Path $venv '.deps-installed'
if (-not (Test-Path $markerFile) -or $Install) {
  Write-Host "Installing Python dependencies..."
  & $venvPy -m pip install --upgrade pip | Out-Null
  & $venvPip install -r (Join-Path $backend 'requirements.txt')
  New-Item -ItemType File -Path $markerFile -Force | Out-Null
}
$backendEnv = Join-Path $backend '.env'
if (-not (Test-Path $backendEnv)) {
  Copy-Item (Join-Path $backend '.env.example') $backendEnv
  Write-Host "Created backend\.env - set your AI key inside" -ForegroundColor Yellow
}

# Автогенерация секретов в backend/.env если placeholder или пусто
function Ensure-Secret {
  param([string]$File, [string]$Name, [ScriptBlock]$Gen, [string[]]$Placeholders)
  $content = Get-Content $File -Raw
  $m = [regex]::Match($content, "(?m)^$Name=(.*)$")
  $current = if ($m.Success) { $m.Groups[1].Value.Trim() } else { "" }
  $needs = (-not $current) -or ($Placeholders -contains $current)
  if ($needs) {
    $new = & $Gen
    if ($m.Success) {
      $content = [regex]::Replace($content, "(?m)^$Name=.*$", "$Name=$new")
    } else {
      $content = $content.TrimEnd() + "`r`n$Name=$new`r`n"
    }
    Set-Content -Path $File -Value $content -NoNewline
    Write-Host "  [secret] generated $Name" -ForegroundColor Yellow
  }
}
$hexGen = { -join ((1..64) | ForEach-Object { "{0:x}" -f (Get-Random -Minimum 0 -Maximum 16) }) }
$fernetGen = {
  & $venvPy -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>$null
}
Ensure-Secret -File $backendEnv -Name 'JWT_SECRET' -Gen $hexGen `
  -Placeholders @('change_this_in_prod_please_min_32_chars_long_secret','change_me')
Ensure-Secret -File $backendEnv -Name 'WA_BRIDGE_SECRET' -Gen $hexGen -Placeholders @('change_me')
Ensure-Secret -File $backendEnv -Name 'SECRET_ENCRYPTION_KEY' -Gen $fernetGen -Placeholders @()

Write-Section "Frontend (React)"
$frontend = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules')) -or $Install) {
  Write-Host "Installing frontend npm packages..."
  Push-Location $frontend
  npm install
  Pop-Location
}

$waBridge = Join-Path $root 'whatsapp-bridge'
if (-not $NoWA) {
  Write-Section "WhatsApp bridge (Node)"
  if (-not (Test-Path (Join-Path $waBridge 'node_modules')) -or $Install) {
    Write-Host "Installing WhatsApp bridge npm packages..."
    Push-Location $waBridge
    npm install
    Pop-Location
  }
  $waEnv = Join-Path $waBridge '.env'
  if (-not (Test-Path $waEnv)) {
    if (Test-Path (Join-Path $waBridge '.env.example')) {
      Copy-Item (Join-Path $waBridge '.env.example') $waEnv
    } else {
      New-Item -ItemType File -Path $waEnv | Out-Null
    }
  }
  # Прокинуть WA_BRIDGE_SECRET из backend/.env в whatsapp-bridge/.env (BRIDGE_SECRET)
  $beContent = Get-Content $backendEnv -Raw
  $waSecMatch = [regex]::Match($beContent, "(?m)^WA_BRIDGE_SECRET=(.*)$")
  if ($waSecMatch.Success) {
    $waSec = $waSecMatch.Groups[1].Value.Trim()
    $waContent = Get-Content $waEnv -Raw
    if ($waContent -match "(?m)^BRIDGE_SECRET=") {
      $waContent = [regex]::Replace($waContent, "(?m)^BRIDGE_SECRET=.*$", "BRIDGE_SECRET=$waSec")
    } else {
      $waContent = ($waContent.TrimEnd() + "`r`nBRIDGE_SECRET=$waSec`r`n")
    }
    Set-Content -Path $waEnv -Value $waContent -NoNewline
  }
}

# Применяем миграции Alembic (sqlite-dev: безопасно)
Write-Section "DB migrations (alembic upgrade head)"
$alembic = Join-Path $venv 'Scripts\alembic.exe'
if (Test-Path $alembic) {
  Push-Location $backend
  $ErrorActionPreference = 'Continue'
  & $alembic upgrade head 2>&1 | ForEach-Object { Write-Host $_ }
  $ErrorActionPreference = 'Stop'
  Pop-Location
}

Write-Section "Starting services"

function Start-Svc {
  param([string]$Name, [string]$File, [string]$SvcArgs, [string]$Wd)
  $logOut = Join-Path $logDir ("{0}.out.log" -f $Name)
  $logErr = Join-Path $logDir ("{0}.err.log" -f $Name)
  $p = Start-Process -FilePath $File -ArgumentList $SvcArgs -WorkingDirectory $Wd `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr `
        -WindowStyle Hidden -PassThru
  Write-Host ("  [OK] {0,-10} PID {1}  log: {2}" -f $Name, $p.Id, $logOut) -ForegroundColor Green
  return $p.Id
}

$pids = @{}

$uvicorn = Join-Path $venv 'Scripts\uvicorn.exe'
$pids.backend = Start-Svc 'backend' $uvicorn 'app.main:app --host 0.0.0.0 --port 8000' $backend

$pids.frontend = Start-Svc 'frontend' 'cmd.exe' '/c npm run dev' $frontend

if (-not $NoWA) {
  $pids.whatsapp = Start-Svc 'whatsapp' 'cmd.exe' '/c npm start' $waBridge
}

$pids | ConvertTo-Json | Set-Content $pidFile

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "All services started." -ForegroundColor Magenta
Write-Host "  UI:       http://localhost:5173" -ForegroundColor Cyan
Write-Host "  API:      http://localhost:8000" -ForegroundColor Cyan
if (-not $NoWA) { Write-Host "  WA bridge: http://localhost:3001" -ForegroundColor Cyan }
Write-Host ""
Write-Host "Logs:     .\logs\*.log"
Write-Host "Stop:     .\start.ps1 -Stop"
Write-Host ""

Start-Process "http://localhost:5173"
