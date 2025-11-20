#!/bin/bash
# Setup NVIDIA Container Toolkit in WSL2 for Docker GPU access
# Run this script inside your WSL2 Ubuntu/Debian distribution

set -e

echo "=========================================="
echo "NVIDIA Container Toolkit Setup for WSL2"
echo "=========================================="
echo ""

# Check if running in WSL2
if ! grep -qi microsoft /proc/version; then
    echo "ERROR: This script must run in WSL2"
    exit 1
fi

echo "[1/6] Checking for NVIDIA GPU..."
if ! nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found in WSL2"
    echo "Make sure you have:"
    echo "  - NVIDIA drivers installed on Windows (already done)"
    echo "  - WSL2 updated to latest version"
    echo ""
    echo "Update WSL2 from PowerShell:"
    echo "  wsl --update"
    exit 1
fi

echo "[OK] NVIDIA GPU detected in WSL2:"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
echo ""

echo "[2/6] Adding NVIDIA Container Toolkit repository..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

echo "[OK] Repository added"
echo ""

echo "[3/6] Updating package list..."
sudo apt-get update
echo "[OK] Package list updated"
echo ""

echo "[4/6] Installing NVIDIA Container Toolkit..."
sudo apt-get install -y nvidia-container-toolkit
echo "[OK] NVIDIA Container Toolkit installed"
echo ""

echo "[5/6] Configuring Docker to use NVIDIA runtime..."
sudo nvidia-ctk runtime configure --runtime=docker
echo "[OK] Docker configured"
echo ""

echo "[6/6] Restarting Docker daemon..."
sudo systemctl restart docker || echo "Note: Docker Desktop manages the daemon, restart not needed"
echo "[OK] Configuration complete"
echo ""

echo "=========================================="
echo "SUCCESS! GPU support enabled"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Exit WSL2 (type 'exit')"
echo "  2. Restart Docker Desktop from Windows"
echo "  3. Run from PowerShell: .\\enable_gpu.ps1"
echo ""
