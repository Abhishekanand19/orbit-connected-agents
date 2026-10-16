$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$vite = Join-Path $PSScriptRoot 'frontend\node_modules\vite\bin\vite.js'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $vite)) {
    throw 'Install the existing Python and frontend dependencies before starting the demo.'
}
$node = (Get-Command node -ErrorAction Stop).Source
function Read-Health {
    try { return Invoke-RestMethod 'http://127.0.0.1:8001/api/health' -TimeoutSec 2 } catch { return $null }
}
function Port-InUse($port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}
$health = Read-Health
if ((Port-InUse 8001) -and (!$health -or $health.graph -ne 'orbit_demo_family')) {
    throw 'Port 8001 belongs to another or unhealthy backend. Stop it explicitly before launching the isolated demo.'
}
if (Port-InUse 5173) {
    try {
        $services = (Invoke-WebRequest 'http://127.0.0.1:5173/src/services.js' -TimeoutSec 2).Content
        if ($services -notmatch 'orbit.workspace.v1' -or $services -match '"VITE_ORBIT_API_URL":\s*"(?!http://127\.0\.0\.1:8001")') {
            throw 'Unexpected frontend configuration'
        }
    } catch { throw 'Port 5173 belongs to an unknown frontend. Stop it explicitly before launching the demo.' }
}
docker compose up -d --wait falkordb
if ($LASTEXITCODE -ne 0) { throw 'FalkorDB failed to become healthy.' }
$logs = Join-Path $env:TEMP 'orbit-demo'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$previousGraph = $env:FALKORDB_GRAPH
$previousApi = $env:VITE_ORBIT_API_URL
try {
    $env:FALKORDB_GRAPH = 'orbit_demo_family'
    $env:VITE_ORBIT_API_URL = 'http://127.0.0.1:8001'
    # Seed is idempotent. Startup never resets a graph or performs provider writes.
    & $python -m backend.orbit.demo
    if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed.' }
    if (!$health) {
        $backend = Start-Process -FilePath $python -ArgumentList '-m uvicorn backend.orbit.api:app --host 127.0.0.1 --port 8001' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'backend.out.log') -RedirectStandardError (Join-Path $logs 'backend.err.log')
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $health = Read-Health
            if ($health) { break }
            if ($backend.HasExited) { throw "Backend exited. Inspect $logs" }
            Start-Sleep -Seconds 1
        }
        if (!$health -or $health.graph -ne 'orbit_demo_family') { throw "Demo health check failed. Inspect $logs" }
    }
    if (!(Port-InUse 5173)) {
        $frontend = Start-Process -FilePath $node -ArgumentList "`"$vite`" --host 127.0.0.1 --port 5173 --strictPort" -WorkingDirectory (Join-Path $PSScriptRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'frontend.out.log') -RedirectStandardError (Join-Path $logs 'frontend.err.log')
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try { $null = Invoke-WebRequest 'http://127.0.0.1:5173' -TimeoutSec 2; $ready = $true; break } catch {}
            if ($frontend.HasExited) { throw "Frontend exited. Inspect $logs" }
            Start-Sleep -Seconds 1
        }
        if (!$ready) { throw "Frontend health check failed. Inspect $logs" }
    }
    Write-Output 'Orbit demo ready: http://127.0.0.1:5173 (backend 8001, isolated persistent graph orbit_demo_family).'
} finally {
    $env:FALKORDB_GRAPH = $previousGraph
    $env:VITE_ORBIT_API_URL = $previousApi
}
