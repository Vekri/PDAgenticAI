$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    py -m venv .venv
}
& $python -c "import fastapi, uvicorn, sklearn, xgboost, pydantic" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r requirements.txt
}
& $python -m uvicorn app.api:app --host 127.0.0.1 --port 8000
