$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn backend.orbit.api:app --host 127.0.0.1 --port 8001
