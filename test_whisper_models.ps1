# Test script to compare all Faster Whisper models on tests/wagonwheel.mp3
# Uses default settings: no VAD, no voice filter, no Demucs vocal separation
# Usage: .\test_whisper_models.ps1

Write-Host "Testing All Faster Whisper Models on tests/wagonwheel.mp3" -ForegroundColor Cyan
Write-Host "Default settings: No VAD, No voice filter, No Demucs separation" -ForegroundColor Gray
Write-Host ("=" * 70)

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Test file
$audioFile = "tests\wagonwheel.mp3"

if (-not (Test-Path $audioFile)) {
    Write-Host "`nError: $audioFile not found!" -ForegroundColor Red
    exit 1
}

# All Faster Whisper models (in order of speed to accuracy)
$models = @("tiny", "base", "small", "medium", "large-v2", "large-v3")

# Track results for summary
$results = @()

foreach ($model in $models) {
    Write-Host "`n`n"
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host "Testing with Whisper model: $model" -ForegroundColor Green
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host ""
    
    # Run extraction with timing (no VAD, no voice filter, no Demucs)
    Write-Host "[SCRIPT] Starting test for $model model..." -ForegroundColor DarkGray
    $startTime = Get-Date
    $output = python -m src.rag.index_lyrics --test $audioFile --whisper-model $model 2>&1
    $exitCode = $LASTEXITCODE
    Write-Host $output
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    # Store result
    $results += [PSCustomObject]@{
        Model = $model
        Duration = $duration
        Status = if ($exitCode -eq 0) { "Success" } else { "Failed" }
    }
    
    Write-Host "`n[SCRIPT] Processing time for $model model: $([math]::Round($duration, 2)) seconds" -ForegroundColor Yellow
    if ($exitCode -ne 0) {
        Write-Host "[SCRIPT] ⚠ Test failed with exit code: $exitCode" -ForegroundColor Red
    }
    Write-Host "[SCRIPT] Completed $model model test`n" -ForegroundColor DarkGray
}

Write-Host "`n`n"
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "TEST SUMMARY" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""

foreach ($result in $results) {
    $statusColor = if ($result.Status -eq "Success") { "Green" } else { "Red" }
    $statusSymbol = if ($result.Status -eq "Success") { "[OK]" } else { "[FAIL]" }
    $timeStr = "{0:F2}s" -f $result.Duration
    Write-Host ("{0,-12} {1,-7} {2,10}" -f $result.Model, $statusSymbol, $timeStr) -ForegroundColor $statusColor
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
