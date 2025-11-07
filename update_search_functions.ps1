# Update Search Functions Migration
# This script applies the updated search functions to return all song information

Write-Host "Updating PostgreSQL search functions..." -ForegroundColor Cyan

# Load database config
$config = Get-Content "config.json" | ConvertFrom-Json

$env:PGHOST = $config.database.host
$env:PGPORT = $config.database.port
$env:PGDATABASE = $config.database.database
$env:PGUSER = $config.database.user
$env:PGPASSWORD = $config.database.password

# Apply migration
Write-Host "Applying migration: update_search_functions.sql" -ForegroundColor Yellow
psql -f "update_search_functions.sql"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSearch functions updated successfully!" -ForegroundColor Green
    Write-Host "The demo_rag_search.py will now show all song information." -ForegroundColor Green
} else {
    Write-Host "`nError updating search functions." -ForegroundColor Red
    exit 1
}
