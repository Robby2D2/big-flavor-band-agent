# Run database migration to change song ID to INTEGER
# This script applies the migration that converts song IDs from VARCHAR to INTEGER

Write-Host "===================================" -ForegroundColor Cyan
Write-Host "Database Migration: Song ID to INTEGER" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "WARNING: This will DROP all existing songs and related data!" -ForegroundColor Yellow
Write-Host "Make sure you have a backup if needed." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Continue? (yes/no)"
if ($confirm -ne "yes" -and $confirm -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "Applying migration..." -ForegroundColor Green

# Get database credentials from environment or use defaults
$DB_HOST = if ($env:DB_HOST) { $env:DB_HOST } else { "localhost" }
$DB_PORT = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$DB_NAME = if ($env:DB_NAME) { $env:DB_NAME } else { "bigflavor" }
$DB_USER = if ($env:DB_USER) { $env:DB_USER } else { "bigflavor" }

$env:PGPASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "bigflavor_dev_pass" }

# Apply migration
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "database\sql\migrations\04-migrate-song-id-to-integer.sql"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Migration applied successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Run the scraper to populate with new data"
    Write-Host "  2. Songs will now use numeric IDs from audio URLs"
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "✗ Migration failed!" -ForegroundColor Red
    Write-Host "Check the error messages above." -ForegroundColor Red
    Write-Host ""
}
