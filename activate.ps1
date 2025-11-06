# Activate Virtual Environment Script
# Quick script to activate the Python virtual environment for this project

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Big Flavor Band - Virtual Environment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$venvPath = ".\venv\Scripts\Activate.ps1"

if (Test-Path $venvPath) {
    Write-Host "Activating virtual environment..." -ForegroundColor Green
    & $venvPath
    
    Write-Host ""
    Write-Host "✓ Virtual environment activated!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Environment Info:" -ForegroundColor Yellow
    python --version
    Write-Host ""
    
    Write-Host "To deactivate later, run: deactivate" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "✗ Virtual environment not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To create it, run:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv" -ForegroundColor White
    Write-Host ""
}
