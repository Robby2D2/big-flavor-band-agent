# Start BigFlavor Backend API
Write-Host "Starting BigFlavor Backend API..." -ForegroundColor Green

# Activate virtual environment
Write-Host "Activating Python virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Check if uvicorn is installed
$uvicornInstalled = python -m pip list | Select-String "uvicorn"
if (-not $uvicornInstalled) {
    Write-Host "Installing API dependencies..." -ForegroundColor Yellow
    python -m pip install -r requirements-api.txt
}

# Start the backend API
Write-Host "Starting FastAPI server on http://localhost:8000" -ForegroundColor Green
Write-Host "API docs available at http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

python backend_api.py
