# Setup script for Big Flavor Band AI Agent
# Run this script to set up your development environment

Write-Host "🎸 Big Flavor Band AI Agent - Setup" -ForegroundColor Cyan
Write-Host "=" -NoNewline; 1..50 | ForEach-Object { Write-Host "=" -NoNewline }; Write-Host ""

# Check Python version
Write-Host "`nChecking Python version..." -ForegroundColor Yellow
python --version

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.10 or higher from https://python.org" -ForegroundColor Red
    exit 1
}

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install requirements
Write-Host "`nInstalling dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "`n✅ Setup completed successfully!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "  1. Run the demo: python example.py" -ForegroundColor White
Write-Host "  2. Start the MCP server: python mcp_server.py" -ForegroundColor White
Write-Host "  3. Read QUICKSTART.md for more examples" -ForegroundColor White
Write-Host "`nRock on! 🤘`n" -ForegroundColor Cyan
