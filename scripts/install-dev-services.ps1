#Requires -RunAsAdministrator
<#
  Installe l'API et le frontend de l'Orchestrateur comme deux vrais services
  Windows (via NSSM) :
    - orchestrator-api  -> uvicorn (port 8000)
    - orchestrator-web  -> next dev (port 3001)

  Les deux démarrent automatiquement au boot de la machine et redémarrent
  seuls en cas de crash (arrêt de Docker Desktop, erreur non gérée, etc.) —
  on ne dépend plus d'un process lancé à la main dans un terminal qui meurt
  au premier redémarrage.

  À exécuter UNE FOIS depuis un PowerShell "Exécuter en tant qu'administrateur",
  à la racine du dépôt cloné :
      .\scripts\install-dev-services.ps1

  Ré-exécutable sans risque (idempotent : recrée les services proprement).
#>

$ErrorActionPreference = "Stop"

# Racine du dépôt déduite de l'emplacement du script (scripts/..) — jamais un
# chemin absolu figé : ce script est versionné, il doit rester valable sur
# n'importe quelle machine où le dépôt est cloné, pas seulement celle où il a
# été écrit.
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$ApiDir    = Join-Path $RepoRoot "orchestrator_api"
$WebDir    = Join-Path $RepoRoot "frontend"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$NextEntry = Join-Path $WebDir "node_modules\next\dist\bin\next"
$LogDir    = Join-Path $RepoRoot "logs"

$NodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $NodeCmd) { throw "Node.js introuvable dans le PATH. Installez-le puis relancez ce script." }
$NodeExe = $NodeCmd.Source

if (-not (Test-Path $PythonExe)) { throw "Python introuvable : $PythonExe (le venv a-t-il été créé à la racine du dépôt ?)" }
if (-not (Test-Path $NextEntry)) { throw "Next.js introuvable : $NextEntry (npm install a-t-il été lancé dans frontend/ ?)" }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --- 1. NSSM (gestionnaire de services génériques, standard en prod Windows) ---
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Host "Installation de NSSM via Chocolatey..."
    choco install nssm -y
    # nssm.exe est installé mais pas encore dans le PATH de cette session
    $env:Path += ";C:\ProgramData\chocolatey\bin"
}

# --- 2. Libère les ports si des process de dev tournent déjà à la main ---
foreach ($port in 8000, 3001) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Host "Arrêt du process qui écoute déjà sur le port $port (PID $($c.OwningProcess))..."
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

function Install-DevService {
    param($Name, $Exe, $Args, $AppDir, $DisplayName, $Description)

    # Idempotent : on repart d'un service propre à chaque exécution du script.
    $existing = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-Service $Name -Force -ErrorAction SilentlyContinue
        nssm remove $Name confirm | Out-Null
    }

    nssm install $Name $Exe $Args
    nssm set $Name AppDirectory $AppDir
    nssm set $Name AppStdout (Join-Path $LogDir "$Name.out.log")
    nssm set $Name AppStderr (Join-Path $LogDir "$Name.err.log")
    nssm set $Name AppRotateFiles 1
    nssm set $Name AppRotateBytes 5242880
    nssm set $Name AppExit Default Restart
    nssm set $Name AppRestartDelay 3000
    nssm set $Name Start SERVICE_AUTO_START
    nssm set $Name DisplayName $DisplayName
    nssm set $Name Description $Description
}

# --- 3. Service API ---
Install-DevService -Name "orchestrator-api" `
    -Exe $PythonExe -Args "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" `
    -AppDir $ApiDir `
    -DisplayName "Hadi - API" `
    -Description "Backend FastAPI de l'Orchestrateur CI/CD. Demarrage auto + redemarrage sur crash."

# --- 4. Service Frontend ---
Install-DevService -Name "orchestrator-web" `
    -Exe $NodeExe -Args "`"$NextEntry`" dev -p 3001" `
    -AppDir $WebDir `
    -DisplayName "Hadi - Interface web" `
    -Description "Frontend Next.js de l'Orchestrateur CI/CD. Demarrage auto + redemarrage sur crash."

# --- 5. Démarrage ---
Start-Service orchestrator-api
Start-Service orchestrator-web

Start-Sleep -Seconds 6
Write-Host ""
Write-Host "--- État des services ---"
Get-Service orchestrator-api, orchestrator-web | Format-Table Name, Status, StartType -AutoSize

Write-Host ""
Write-Host "--- Vérification santé ---"
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "API   : $($r.StatusCode) $($r.Content)"
} catch { Write-Host "API pas encore prête : $($_.Exception.Message)" }
try {
    $r = Invoke-WebRequest -Uri "http://localhost:3001" -UseBasicParsing -TimeoutSec 5
    Write-Host "Web   : $($r.StatusCode)"
} catch { Write-Host "Frontend pas encore prêt : $($_.Exception.Message)" }

Write-Host ""
Write-Host "Terminé. Logs dans $LogDir\"
Write-Host "Commandes utiles : Get-Service orchestrator-*  |  Restart-Service orchestrator-api  |  nssm edit orchestrator-api"
