# Ollama Model Setup Script (Windows)
# Downloads and configures local LLM models for BigFlavor Band Agent

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Ollama Model Setup for BigFlavor" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
} catch {
    Write-Host "ERROR: Docker is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

# Check if Ollama container is running
$ollamaRunning = docker ps | Select-String "bigflavor-ollama"

if (-not $ollamaRunning) {
    Write-Host "Starting Ollama container..." -ForegroundColor Yellow
    docker-compose up -d ollama
    Write-Host "Waiting for Ollama to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
}

# Get model name from environment or use default
$MODEL = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "llama3.1:8b" }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Downloading Model: $MODEL" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This may take several minutes depending on model size:" -ForegroundColor Yellow
Write-Host "  - llama3.2:3b  ~2GB  (Fastest, good for basic tasks)"
Write-Host "  - mistral:7b   ~4GB  (Balanced)"
Write-Host "  - llama3.1:8b  ~4.7GB (Recommended, best quality/speed ratio)" -ForegroundColor Green
Write-Host "  - codellama:13b ~7GB  (Better for music/code, slower)"
Write-Host ""

# Pull the model
Write-Host "Downloading model (this may take a while)..." -ForegroundColor Yellow
docker exec bigflavor-ollama ollama pull $MODEL

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Model Download Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

# Test the model
Write-Host "Testing model..." -ForegroundColor Yellow
docker exec bigflavor-ollama ollama run $MODEL "Say 'Hello, I am ready to help with BigFlavor!'"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your local LLM is ready to use." -ForegroundColor Cyan
Write-Host ""
Write-Host "To use this model in production:" -ForegroundColor Yellow
Write-Host "  1. Set LLM_PROVIDER=ollama in .env.production"
Write-Host "  2. Set OLLAMA_MODEL=$MODEL in .env.production"
Write-Host "  3. Deploy: .\deploy-production.ps1"
Write-Host ""
Write-Host "Available models installed:" -ForegroundColor Cyan
docker exec bigflavor-ollama ollama list
Write-Host ""
Write-Host "To download additional models:" -ForegroundColor Yellow
Write-Host "  docker exec bigflavor-ollama ollama pull <model-name>"
Write-Host ""
Write-Host "Popular models:" -ForegroundColor Cyan
Write-Host "  - llama3.2:3b    (Small, fast)"
Write-Host "  - mistral:7b     (Medium, balanced)"
Write-Host "  - llama3.1:8b    (Recommended)" -ForegroundColor Green
Write-Host "  - codellama:13b  (Large, best quality)"
Write-Host ""
Write-Host "Browse all models: https://ollama.com/library" -ForegroundColor Cyan
Write-Host ""
