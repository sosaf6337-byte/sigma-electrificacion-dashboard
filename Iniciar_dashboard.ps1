$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Falta el entorno Python. Consulte README.md para instalarlo.' }
$workPath = Join-Path $projectPath 'work'
New-Item -ItemType Directory -Path $workPath -Force | Out-Null
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2
    if ($health.model_version) { Write-Output 'Dashboard disponible: http://127.0.0.1:8765'; exit 0 }
} catch {}
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','sigma_dashboard.app:app','--host','127.0.0.1','--port','8765','--no-access-log') -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $workPath 'server.log') -RedirectStandardError (Join-Path $workPath 'server-error.log') -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $workPath 'server.pid')
Write-Output 'Iniciando dashboard en http://127.0.0.1:8765'
