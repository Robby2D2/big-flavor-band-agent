# Enable GPU for Ollama and verify it's working

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Enabling GPU for Ollama" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if GPU exists on host
Write-Host "Checking for NVIDIA GPU on host..." -ForegroundColor Yellow
try {
    $gpuInfo = nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] GPU Found: $gpuInfo" -ForegroundColor Green
    } else {
        Write-Host "[WARN] nvidia-smi not found or GPU not detected" -ForegroundColor Yellow
        Write-Host "Make sure NVIDIA drivers are installed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Could not detect GPU" -ForegroundColor Yellow
}

Write-Host ""

# Stop Ollama
Write-Host "Stopping Ollama container..." -ForegroundColor Yellow
docker-compose down ollama

Write-Host ""

# Start Ollama with GPU
Write-Host "Starting Ollama with GPU support..." -ForegroundColor Yellow
docker-compose up -d ollama

Write-Host ""
Write-Host "Waiting for Ollama to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

Write-Host ""

# Verify GPU is accessible
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Verifying GPU Access" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking if GPU is visible in container..." -ForegroundColor Yellow
$gpuCheck = docker exec bigflavor-ollama nvidia-smi 2>&1

if ($gpuCheck -match "NVIDIA-SMI") {
    Write-Host ""
    Write-Host "SUCCESS! GPU is accessible in Ollama container!" -ForegroundColor Green
    Write-Host ""
    docker exec bigflavor-ollama nvidia-smi
    Write-Host ""
    Write-Host "Your RTX 3090 is ready for blazing-fast inference!" -ForegroundColor Green
    Write-Host "Expect 10-20x faster performance than CPU!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "GPU not detected in container" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "This could mean:" -ForegroundColor Yellow
    Write-Host "  1. GPU support not enabled in Docker Desktop" -ForegroundColor White
    Write-Host "  2. NVIDIA Container Toolkit not installed" -ForegroundColor White
    Write-Host "  3. WSL2 integration not configured" -ForegroundColor White
    Write-Host ""
    Write-Host "Follow the guide: ENABLE_GPU.md" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Quick fix for Docker Desktop 4.50+:" -ForegroundColor Cyan
    Write-Host "  1. Open Docker Desktop Settings" -ForegroundColor White
    Write-Host "  2. Go to Resources -> Advanced" -ForegroundColor White
    Write-Host "  3. Enable 'GPU support'" -ForegroundColor White
    Write-Host "  4. Restart Docker Desktop" -ForegroundColor White
    Write-Host "  5. Run this script again" -ForegroundColor White
    Write-Host ""
    Write-Host "Ollama will work on CPU (slower but functional)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Container Status" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
docker ps --filter "name=ollama" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host ""
Write-Host "To test the agent, run: .\run_local.ps1" -ForegroundColor Cyan
Write-Host ""
