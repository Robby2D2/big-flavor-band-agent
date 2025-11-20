# Run Full BigFlavorAgent with Ollama + Database
# Complete music search and analysis capabilities!

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BigFlavor Agent - Full Version" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker
Write-Host "Checking prerequisites..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "  [OK] Docker running" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Docker not running" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop" -ForegroundColor Yellow
    exit 1
}

# Check PostgreSQL
$postgresRunning = docker ps --filter "name=bigflavor-postgres" --filter "status=running" --format "{{.Names}}"
if (-not $postgresRunning) {
    Write-Host "  [INFO] Starting PostgreSQL..." -ForegroundColor Yellow
    docker-compose up -d postgres
    Start-Sleep -Seconds 10
} else {
    Write-Host "  [OK] PostgreSQL running" -ForegroundColor Green
}

# Check Ollama
$ollamaRunning = docker ps --filter "name=bigflavor-ollama" --filter "status=running" --format "{{.Names}}"
if (-not $ollamaRunning) {
    Write-Host "  [INFO] Starting Ollama..." -ForegroundColor Yellow
    docker-compose up -d ollama
    Start-Sleep -Seconds 10
} else {
    Write-Host "  [OK] Ollama running" -ForegroundColor Green
}

# Check llama3.1:8b model
$models = docker exec bigflavor-ollama ollama list 2>$null
if ($models -match "llama3.1:8b") {
    Write-Host "  [OK] llama3.1:8b model available" -ForegroundColor Green
} else {
    Write-Host "  [WARN] llama3.1:8b not found, using default model" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Launching BigFlavorAgent..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Activate virtual environment and run
& .\venv\Scripts\python.exe run_full_agent.py

Write-Host ""
Write-Host "Session ended." -ForegroundColor Cyan
