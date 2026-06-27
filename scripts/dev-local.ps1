# Always operate from the repo root (this script lives in scripts/).
Set-Location (Split-Path -Parent $PSScriptRoot)

# dev-local.ps1
# Brings up just the backing services in Docker (PostgreSQL + Icecast/Liquidsoap
# radio stack) so you can run the FastAPI backend and Next.js frontend on the
# host, talking to Anthropic instead of a local LLM.
#
# Requires docker-compose.override.yml (copy it from the .example once):
#   cp docker-compose.override.yml.example docker-compose.override.yml

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BigFlavor - Local Dev (host app, Docker infra)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Docker check
try {
    docker info | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Docker is not running - start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}

# Override must be present, or `up` would try to run the in-container app + Ollama.
if (-not (Test-Path "docker-compose.override.yml")) {
    Write-Host "[INFO] docker-compose.override.yml not found - creating it from the example." -ForegroundColor Yellow
    Copy-Item "docker-compose.override.yml.example" "docker-compose.override.yml"
}

# .env sanity (host backend reads it via python-dotenv)
if (-not (Test-Path ".env")) {
    Write-Host "[WARN] .env not found - copy .env.example to .env and set ANTHROPIC_API_KEY." -ForegroundColor Yellow
} else {
    $envText = Get-Content .env -Raw
    if ($envText -notmatch "LLM_PROVIDER\s*=\s*anthropic") {
        Write-Host "[WARN] LLM_PROVIDER is not 'anthropic' in .env - the host backend may try to use Ollama." -ForegroundColor Yellow
    }
    if ($envText -notmatch "ANTHROPIC_API_KEY\s*=\s*\S") {
        Write-Host "[WARN] ANTHROPIC_API_KEY looks empty in .env." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Starting backing services (postgres + icecast + liquidsoap)..." -ForegroundColor Yellow
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] docker-compose up failed - see output above." -ForegroundColor Red
    exit 1
}

Write-Host ""
docker-compose ps
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Infra is up. Now run the app on the host:" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Backend :  uvicorn backend_api:app --reload --port 8000" -ForegroundColor White
Write-Host "             (or: .\scripts\start-backend.ps1)" -ForegroundColor DarkGray
Write-Host "  Frontend:  cd frontend; npm run dev      # http://localhost:3000" -ForegroundColor White
Write-Host "             (or: .\scripts\start-frontend.ps1)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Stop infra later with:  docker-compose down" -ForegroundColor Cyan
Write-Host ""
