$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath "frontend/dist/index.html")) {
    Push-Location frontend
    try { npm ci; if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }; npm run build; if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" } } finally { Pop-Location }
}
Write-Host "Open http://127.0.0.1:8765 in your browser. Ctrl+C stops the server."
python backend/server.py
