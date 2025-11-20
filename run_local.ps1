# Simple Local Runner for BigFlavor Agent with Ollama
# No production deployment needed - just agent + Ollama!

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BigFlavor Agent - Local Dev Mode" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "[OK] Docker is running" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Docker is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Check if Ollama container is running
Write-Host "Checking Ollama..." -ForegroundColor Yellow
$ollamaRunning = docker ps --filter "name=bigflavor-ollama" --filter "status=running" --format "{{.Names}}"

if (-not $ollamaRunning) {
    Write-Host "[INFO] Ollama not running. Starting Ollama..." -ForegroundColor Yellow
    docker-compose up -d ollama
    Write-Host "Waiting for Ollama to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
} else {
    Write-Host "[OK] Ollama is running" -ForegroundColor Green
}

Write-Host ""

# Check if llama3.1:8b model is installed
Write-Host "Checking for llama3.1:8b model..." -ForegroundColor Yellow
$models = docker exec bigflavor-ollama ollama list
if ($models -match "llama3.1:8b") {
    Write-Host "[OK] llama3.1:8b model is installed" -ForegroundColor Green
} else {
    Write-Host "[INFO] llama3.1:8b model not found. Downloading..." -ForegroundColor Yellow
    Write-Host "This will download ~4.9GB. Please wait..." -ForegroundColor Yellow
    docker exec bigflavor-ollama ollama pull llama3.1:8b
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Starting Chat Session..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Run the local chat
& .\venv\Scripts\python.exe run_agent_local.py

Write-Host ""
Write-Host "Session ended." -ForegroundColor Cyan
