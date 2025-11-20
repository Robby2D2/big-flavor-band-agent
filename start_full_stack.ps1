# Start Full BigFlavor Stack with Ollama
# Runs: PostgreSQL + Ollama + Backend API + Frontend + Nginx

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BigFlavor - Full Stack Startup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker
Write-Host "[1/6] Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "  [OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Docker not running" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Check .env file
Write-Host "[2/6] Checking configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    $envContent = Get-Content .env
    if ($envContent -match "LLM_PROVIDER=ollama") {
        Write-Host "  [OK] Configured to use Ollama (FREE!)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] LLM_PROVIDER not set to ollama" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [FAIL] .env file not found" -ForegroundColor Red
    Write-Host "  Please copy .env.example to .env" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Stop any existing containers
Write-Host "[3/6] Stopping existing containers..." -ForegroundColor Yellow
docker-compose down 2>$null
Write-Host "  [OK] Cleanup complete" -ForegroundColor Green

Write-Host ""

# Start services
Write-Host "[4/6] Starting services..." -ForegroundColor Yellow
Write-Host "  This will start:" -ForegroundColor Cyan
Write-Host "    - PostgreSQL (database)" -ForegroundColor White
Write-Host "    - Ollama (LLM - llama3.1:8b)" -ForegroundColor White
Write-Host "    - Backend API (Python FastAPI)" -ForegroundColor White
Write-Host "    - Frontend (Next.js)" -ForegroundColor White
Write-Host "    - Nginx (reverse proxy)" -ForegroundColor White
Write-Host ""

docker-compose --env-file .env up -d --build

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  [FAIL] Failed to start services" -ForegroundColor Red
    Write-Host "  Check logs with: docker-compose logs" -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] Services starting..." -ForegroundColor Green
Write-Host ""

# Wait for services to be healthy
Write-Host "[5/6] Waiting for services to be healthy..." -ForegroundColor Yellow
Write-Host "  This may take 30-60 seconds..." -ForegroundColor Cyan
Start-Sleep -Seconds 20

$maxRetries = 30
$retry = 0
$allHealthy = $false

while ($retry -lt $maxRetries) {
    $postgresHealth = docker inspect bigflavor-postgres --format='{{.State.Health.Status}}' 2>$null
    $ollamaHealth = docker inspect bigflavor-ollama --format='{{.State.Health.Status}}' 2>$null
    $backendHealth = docker inspect bigflavor-backend --format='{{.State.Health.Status}}' 2>$null

    Write-Host "  Postgres: $postgresHealth | Ollama: $ollamaHealth | Backend: $backendHealth" -ForegroundColor Gray

    if ($postgresHealth -eq "healthy" -and $ollamaHealth -eq "healthy" -and $backendHealth -eq "healthy") {
        $allHealthy = $true
        break
    }

    Start-Sleep -Seconds 5
    $retry++
}

if ($allHealthy) {
    Write-Host "  [OK] All services healthy!" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Some services still starting..." -ForegroundColor Yellow
    Write-Host "  You can check status with: docker-compose ps" -ForegroundColor Cyan
}

Write-Host ""

# Check status
Write-Host "[6/6] Service Status..." -ForegroundColor Yellow
docker-compose ps

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Stack Started Successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Access the application:" -ForegroundColor Cyan
Write-Host "  Web Interface:  http://localhost" -ForegroundColor White
Write-Host "  Backend API:    http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs:       http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "LLM Provider:" -ForegroundColor Cyan
Write-Host "  Using: Ollama (llama3.1:8b)" -ForegroundColor White
Write-Host "  Cost:  $0.00 per request (FREE!)" -ForegroundColor Green
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  View logs (all):       docker-compose logs -f" -ForegroundColor White
Write-Host "  View logs (backend):   docker-compose logs -f backend" -ForegroundColor White
Write-Host "  View logs (ollama):    docker-compose logs -f ollama" -ForegroundColor White
Write-Host "  Stop services:         docker-compose down" -ForegroundColor White
Write-Host "  Restart service:       docker-compose restart backend" -ForegroundColor White
Write-Host ""
Write-Host "Database Info:" -ForegroundColor Cyan
$songCount = docker exec bigflavor-postgres psql -U bigflavor -d bigflavor -t -c "SELECT COUNT(*) FROM songs;" 2>$null
if ($songCount) {
    Write-Host "  Songs in catalog: $($songCount.Trim())" -ForegroundColor White
}
Write-Host ""
