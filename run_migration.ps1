# Run database migration to add song details tables
$sqlFile = "sql\init\02-add-song-details.sql"
$containerName = "bigflavor-postgres"

Write-Host "Running database migration from $sqlFile..."

# Read the SQL file content
$sqlContent = Get-Content $sqlFile -Raw

# Execute the SQL in the container using PowerShell piping
$sqlContent | docker exec -i $containerName psql -U bigflavor -d bigflavor

Write-Host "Migration complete!"
