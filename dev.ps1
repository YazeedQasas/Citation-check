# Starts the API (new window) and the Vite dev server (this window) with ONE command:  .\dev.ps1
# It uses whichever `python` this terminal uses, so the API runs in the same environment as `pip install -e .[api]`.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = (Get-Command python).Source

& $py -c "import fastapi, uvicorn, citation_check" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Missing packages for $py. Run:  python -m pip install -e '.[api]'" -ForegroundColor Red
    exit 1
}

$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host "Port 8000 is already in use (the API may already be running). Skipping API start." -ForegroundColor Yellow
} else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; `$env:PYTHONIOENCODING='utf-8'; & '$py' -m citation_check serve"
    Write-Host "API starting in a new window on http://127.0.0.1:8000"
    Start-Sleep -Seconds 3
}

Set-Location (Join-Path $root "web")
if (-not (Test-Path node_modules)) { npm install }
npm run dev
