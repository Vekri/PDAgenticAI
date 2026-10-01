$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    py -m venv .venv
}
& $python -c "import streamlit, fastapi, sklearn, xgboost, pydantic" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r requirements.txt
}
& $python -m streamlit run 09_desk\ui.py
