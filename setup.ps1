# Setup Script for Windows PowerShell

Write-Host "🎸 Big Flavor Band Agent - Setup Script 🎸" -ForegroundColor Cyan
Write-Host ""

# Check Node.js installation
Write-Host "Checking Node.js installation..." -ForegroundColor Yellow
$nodeVersion = node --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Node.js is not installed!" -ForegroundColor Red
    Write-Host "Please install Node.js 18 or higher from https://nodejs.org/" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Node.js $nodeVersion found" -ForegroundColor Green

# Check npm installation
Write-Host "Checking npm installation..." -ForegroundColor Yellow
$npmVersion = npm --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ npm is not installed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ npm $npmVersion found" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Dependencies installed successfully" -ForegroundColor Green
Write-Host ""

# Check for .env file
Write-Host "Checking environment configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "✅ .env file found" -ForegroundColor Green
} else {
    Write-Host "⚠️  .env file not found" -ForegroundColor Yellow
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "✅ .env file created" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠️  IMPORTANT: Please edit .env and add your OpenAI API key!" -ForegroundColor Yellow
    Write-Host "   Open .env and replace 'your_openai_api_key_here' with your actual key." -ForegroundColor Yellow
    Write-Host ""
}

# Build the project
Write-Host "Building the project..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Project built successfully" -ForegroundColor Green
Write-Host ""

# Display next steps
Write-Host "🎉 Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Edit .env file and add your OpenAI API key" -ForegroundColor White
Write-Host "  2. Run 'npm start' to launch the interactive CLI" -ForegroundColor White
Write-Host "  3. Check out README.md for more information" -ForegroundColor White
Write-Host ""
Write-Host "Quick commands:" -ForegroundColor Cyan
Write-Host "  npm start       - Start interactive CLI" -ForegroundColor White
Write-Host "  npm run examples - Run example scripts" -ForegroundColor White
Write-Host "  npm run start:mcp - Start MCP server only" -ForegroundColor White
Write-Host ""
Write-Host "Rock on! 🤘" -ForegroundColor Magenta
