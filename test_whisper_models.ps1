# Test script to compare all Faster Whisper models on tests/wagonwheel.mp3
# Uses default settings: no VAD, no voice filter, no Demucs vocal separation
# Usage: .\test_whisper_models.ps1

Write-Host "Testing All Faster Whisper Models on tests/wagonwheel.mp3" -ForegroundColor Cyan
Write-Host "Default settings: No VAD, No voice filter, No Demucs separation" -ForegroundColor Gray
Write-Host "=" * 70

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

foreach ($model in $models) {
    Write-Host "`n`n" -NoNewline
    Write-Host "=" * 70 -ForegroundColor Cyan
    Write-Host "Testing with Whisper model: $model" -ForegroundColor Green
    Write-Host "=" * 70 -ForegroundColor Cyan
    Write-Host ""
    
    # Run extraction with timing (no VAD, no voice filter, no Demucs)
    $startTime = Get-Date
    python -m src.rag.index_lyrics --test $audioFile --whisper-model $model
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    Write-Host "`nProcessing time for $model model: $([math]::Round($duration, 2)) seconds" -ForegroundColor Yellow
    Write-Host "`nPress any key to continue to next model..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host "`n`nAll tests completed!" -ForegroundColor Green
Write-Host "Tested models: $($models -join ', ')" -ForegroundColor Cyan
