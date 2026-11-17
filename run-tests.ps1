$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -m unittest discover -s backend -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
Push-Location frontend
try {
    if (-not (Test-Path -LiteralPath node_modules)) {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    }
    npm test
    if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
} finally { Pop-Location }
Write-Host "All tests and the production build passed."
