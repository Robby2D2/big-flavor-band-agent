# Setup script for PostgreSQL database

Write-Host '' -ForegroundColor Green
Write-Host '========================================' -ForegroundColor Cyan
Write-Host 'Setting up PostgreSQL with pgvector' -ForegroundColor Yellow
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

# Start Docker Compose
Write-Host 'Starting Docker containers...' -ForegroundColor Yellow
docker compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host 'Failed to start Docker containers' -ForegroundColor Red
    Write-Host 'Make sure Docker Desktop is running!' -ForegroundColor Yellow
    exit 1
}

# Wait for database to be ready
Write-Host ''
Write-Host 'Waiting for database to be ready...' -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check if database is running
Write-Host ''
Write-Host 'Checking container status...' -ForegroundColor Yellow
docker compose ps

# Install Python dependencies
Write-Host ''
Write-Host 'Installing Python dependencies...' -ForegroundColor Yellow
pip install asyncpg

if ($LASTEXITCODE -ne 0) {
    Write-Host 'Failed to install dependencies' -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host 'Setup complete!' -ForegroundColor Green
Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host 'Database Connection Details' -ForegroundColor Yellow
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  Host: localhost' -ForegroundColor White
Write-Host '  Port: 5432' -ForegroundColor White
Write-Host '  Database: bigflavor' -ForegroundColor White
Write-Host '  User: bigflavor' -ForegroundColor White
Write-Host '  Password: bigflavor_dev_pass' -ForegroundColor White
Write-Host ''

Write-Host 'To test the database connection, run:' -ForegroundColor Cyan
Write-Host '  python db_example.py' -ForegroundColor White
Write-Host ''

Write-Host 'To stop the database:' -ForegroundColor Cyan
Write-Host '  docker compose down' -ForegroundColor White
Write-Host ''
