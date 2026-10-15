$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. .\aws-project.ps1
$env:PATHLOCK_RUNTIME = '1'
& .\.venv\Scripts\python.exe -m uvicorn backend.server:app --host 127.0.0.1 --port 8000
