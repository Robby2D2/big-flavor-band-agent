# BigFlavor Band Agent - Production Deployment Script (Windows)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BigFlavor Band Agent - Production Deploy" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env.production exists
if (-not (Test-Path ".env.production")) {
    Write-Host "ERROR: .env.production file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.production.example to .env.production and configure it:" -ForegroundColor Yellow
    Write-Host "  copy .env.production.example .env.production"
    Write-Host "  notepad .env.production"
    exit 1
}

# Check if audio_library exists
if (-not (Test-Path "audio_library")) {
    Write-Host "WARNING: audio_library directory not found!" -ForegroundColor Yellow
    Write-Host "Creating empty audio_library directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "audio_library" | Out-Null
}

# Read and check environment variables
$envContent = Get-Content .env.production
$envVars = @{}
foreach ($line in $envContent) {
    if ($line -match '^([^=]+)=(.*)$') {
        $envVars[$matches[1]] = $matches[2]
    }
}

# Check critical environment variables
$missingVars = 0

if (-not $envVars["ANTHROPIC_API_KEY"] -or $envVars["ANTHROPIC_API_KEY"] -like "*xxxxx*") {
    Write-Host "ERROR: ANTHROPIC_API_KEY not configured" -ForegroundColor Red
    $missingVars++
}

if (-not $envVars["AUTH0_SECRET"] -or $envVars["AUTH0_SECRET"] -like "*your_long_random*") {
    Write-Host "ERROR: AUTH0_SECRET not configured" -ForegroundColor Red
    Write-Host "Generate one with PowerShell:" -ForegroundColor Yellow
    Write-Host '  -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | % {[char]$_})' -ForegroundColor Cyan
    $missingVars++
}

if (-not $envVars["AUTH0_CLIENT_ID"] -or $envVars["AUTH0_CLIENT_ID"] -like "*your_client_id*") {
    Write-Host "ERROR: AUTH0_CLIENT_ID not configured" -ForegroundColor Red
    $missingVars++
}

if ($missingVars -gt 0) {
    Write-Host ""
    Write-Host "Please configure all required variables in .env.production" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Environment configuration validated" -ForegroundColor Green
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker is not running" -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Ask for confirmation
Write-Host "This will:" -ForegroundColor Yellow
Write-Host "  1. Build Docker images for all services"
Write-Host "  2. Start services on port 80"
Write-Host "  3. Set up the database with migrations"
Write-Host ""
$confirmation = Read-Host "Continue? (y/n)"
if ($confirmation -ne 'y' -and $confirmation -ne 'Y') {
    Write-Host "Deployment cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Building Docker images..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
docker-compose --env-file .env.production build

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Starting services..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
docker-compose --env-file .env.production up -d

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Waiting for services to be healthy..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Start-Sleep -Seconds 10

# Pull the local LLM model when running with the Ollama provider.
# The model is required for the agent to work, so we download it as part of
# the deploy instead of relying on a separate manual setup step.
$llmProvider = if ($envVars["LLM_PROVIDER"]) { $envVars["LLM_PROVIDER"] } else { "anthropic" }
if ($llmProvider -eq "ollama") {
    $ollamaModel = if ($envVars["OLLAMA_MODEL"]) { $envVars["OLLAMA_MODEL"] } else { "qwen2.5:14b" }
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "Pulling Ollama model: $ollamaModel" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "(first run downloads several GB - this can take a while)" -ForegroundColor Yellow

    # Wait for the Ollama API to come up before pulling.
    $ollamaReady = $false
    for ($i = 1; $i -le 30; $i++) {
        docker exec bigflavor-ollama ollama list 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $ollamaReady = $true; break }
        Write-Host "Waiting for Ollama to be ready... ($i/30)"
        Start-Sleep -Seconds 5
    }

    if (-not $ollamaReady) {
        Write-Host "WARNING: Ollama did not become ready in time." -ForegroundColor Yellow
        Write-Host "Pull the model manually once it is up:" -ForegroundColor Yellow
        Write-Host "  docker exec bigflavor-ollama ollama pull $ollamaModel" -ForegroundColor Cyan
    } else {
        $installed = docker exec bigflavor-ollama ollama list 2>$null | Select-String ([regex]::Escape($ollamaModel))
        if ($installed) {
            Write-Host "✓ Model $ollamaModel already present" -ForegroundColor Green
        } else {
            docker exec bigflavor-ollama ollama pull $ollamaModel
            Write-Host "✓ Model $ollamaModel ready" -ForegroundColor Green
        }
    }
}

# Check service health
$retries = 30
$count = 0
$healthy = $false

while ($count -lt $retries) {
    $status = docker-compose ps
    if ($status -match "healthy") {
        Write-Host "✓ Services are healthy" -ForegroundColor Green
        $healthy = $true
        break
    }
    Write-Host "Waiting for health checks... ($($count+1)/$retries)"
    Start-Sleep -Seconds 5
    $count++
}

if (-not $healthy) {
    Write-Host "WARNING: Health checks taking longer than expected" -ForegroundColor Yellow
    Write-Host "Check logs with: docker-compose logs -f" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Deployment Status" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
docker-compose ps

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your application is now running on:" -ForegroundColor Cyan
Write-Host "  http://localhost (or your server IP)" -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  View logs:           docker-compose logs -f"
Write-Host "  Stop services:       docker-compose down"
Write-Host "  Restart service:     docker-compose restart [service]"
Write-Host "  View this guide:     cat DOCKER_DEPLOYMENT.md"
Write-Host ""
Write-Host "Check service health:" -ForegroundColor Cyan
Write-Host "  curl http://localhost/health"
Write-Host ""
