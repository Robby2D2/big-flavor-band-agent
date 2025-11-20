# Complete GPU Setup Script for Windows + Docker Desktop + WSL2
# This handles everything needed to get Ollama using your RTX 3090

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Complete GPU Setup for Ollama" -ForegroundColor Cyan
Write-Host "RTX 3090 GPU Acceleration" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check prerequisites
Write-Host "[Step 1/5] Checking prerequisites..." -ForegroundColor Yellow
Write-Host ""

# Check Docker Desktop
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
    Write-Host "  [OK] Docker Desktop: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Docker Desktop not running" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop first" -ForegroundColor Yellow
    exit 1
}

# Check WSL2
try {
    $wslVersion = wsl --status 2>$null
    if ($wslVersion -match "WSL 2") {
        Write-Host "  [OK] WSL2 is enabled" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] WSL2 not detected" -ForegroundColor Red
        Write-Host "  Enable WSL2 with: wsl --set-default-version 2" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "  [FAIL] WSL not installed" -ForegroundColor Red
    exit 1
}

# Check GPU on host
try {
    $gpu = nvidia-smi --query-gpu=name --format=csv,noheader 2>$null
    Write-Host "  [OK] GPU detected: $gpu" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] NVIDIA GPU not detected" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 2: Check if nvidia-smi works in WSL2
Write-Host "[Step 2/5] Checking GPU access in WSL2..." -ForegroundColor Yellow
$wslGpu = wsl nvidia-smi --query-gpu=name --format=csv,noheader 2>$null

if ($wslGpu) {
    Write-Host "  [OK] GPU accessible in WSL2: $wslGpu" -ForegroundColor Green
} else {
    Write-Host "  [WARN] GPU not accessible in WSL2" -ForegroundColor Yellow
    Write-Host "  Updating WSL2..." -ForegroundColor Yellow
    wsl --update
    Write-Host "  Please restart your computer, then run this script again" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Step 3: Install NVIDIA Container Toolkit in WSL2
Write-Host "[Step 3/5] Setting up NVIDIA Container Toolkit..." -ForegroundColor Yellow

# Check if already installed
$toolkitInstalled = wsl bash -c "which nvidia-ctk" 2>$null

if ($toolkitInstalled) {
    Write-Host "  [OK] NVIDIA Container Toolkit already installed" -ForegroundColor Green
} else {
    Write-Host "  Installing NVIDIA Container Toolkit in WSL2..." -ForegroundColor Yellow
    Write-Host "  This will prompt for sudo password..." -ForegroundColor Cyan
    Write-Host ""

    # Run setup script in WSL2
    $setupScript = Get-Content .\setup_gpu_wsl2.sh -Raw
    $setupScript | wsl bash

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  [OK] NVIDIA Container Toolkit installed" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "  [FAIL] Installation failed" -ForegroundColor Red
        Write-Host "  Try running manually in WSL2:" -ForegroundColor Yellow
        Write-Host "    wsl" -ForegroundColor Cyan
        Write-Host "    bash setup_gpu_wsl2.sh" -ForegroundColor Cyan
        exit 1
    }
}

Write-Host ""

# Step 4: Restart Docker Desktop
Write-Host "[Step 4/5] Restarting Docker Desktop..." -ForegroundColor Yellow
Write-Host "  Stopping Docker Desktop..." -ForegroundColor Cyan

# Try to restart Docker Desktop
try {
    Stop-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5

    # Start Docker Desktop
    $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerPath) {
        Start-Process $dockerPath
        Write-Host "  Waiting for Docker to start..." -ForegroundColor Cyan
        Start-Sleep -Seconds 20
    }
} catch {
    Write-Host "  [WARN] Could not restart Docker Desktop automatically" -ForegroundColor Yellow
    Write-Host "  Please restart Docker Desktop manually, then press Enter" -ForegroundColor Yellow
    Read-Host
}

# Wait for Docker to be ready
$attempts = 0
while ($attempts -lt 30) {
    try {
        docker info | Out-Null
        Write-Host "  [OK] Docker is ready" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 2
        $attempts++
    }
}

Write-Host ""

# Step 5: Restart Ollama with GPU
Write-Host "[Step 5/5] Restarting Ollama with GPU support..." -ForegroundColor Yellow
docker-compose down ollama
Start-Sleep -Seconds 2
docker-compose up -d ollama

Write-Host "  Waiting for Ollama to start..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Testing GPU Access" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Test if GPU is visible in container
$gpuTest = docker exec bigflavor-ollama nvidia-smi 2>&1

if ($gpuTest -match "NVIDIA-SMI") {
    Write-Host "SUCCESS! GPU is now accessible in Ollama!" -ForegroundColor Green
    Write-Host ""
    docker exec bigflavor-ollama nvidia-smi
    Write-Host ""
    Write-Host "Your RTX 3090 is ready!" -ForegroundColor Green
    Write-Host "Expected speedup: 10-20x faster than CPU" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "GPU still not detected in container" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Additional troubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Check Docker Desktop Settings -> Resources" -ForegroundColor White
    Write-Host "  2. Ensure WSL2 integration is enabled" -ForegroundColor White
    Write-Host "  3. Try restarting your computer" -ForegroundColor White
    Write-Host ""
    Write-Host "Checking Ollama logs:" -ForegroundColor Cyan
    docker logs bigflavor-ollama 2>&1 | Select-String -Pattern "cuda|gpu|nvidia" -CaseSensitive:$false | Select-Object -Last 5
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Setup Complete" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test the agent with GPU:" -ForegroundColor Cyan
Write-Host "  .\run_local.ps1" -ForegroundColor White
Write-Host ""
Write-Host "To verify GPU is being used:" -ForegroundColor Cyan
Write-Host "  docker exec bigflavor-ollama nvidia-smi" -ForegroundColor White
Write-Host ""
