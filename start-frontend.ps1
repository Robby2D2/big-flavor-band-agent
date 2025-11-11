# Start BigFlavor Frontend
Write-Host "Starting BigFlavor Frontend..." -ForegroundColor Green

# Navigate to frontend directory
Set-Location frontend

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}

# Check if .env.local exists
if (-not (Test-Path ".env.local")) {
    Write-Host ""
    Write-Host "WARNING: .env.local file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.example to .env.local and configure it" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to continue anyway..."
}

# Start the frontend
Write-Host ""
Write-Host "Starting Next.js frontend on http://localhost:3000" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

npm run dev
