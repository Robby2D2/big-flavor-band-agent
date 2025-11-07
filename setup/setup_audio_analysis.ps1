# Audio Analysis Setup Script
# Installs optional audio analysis dependencies

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Big Flavor Band - Audio Analysis Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "This script will install the optional audio analysis dependencies:" -ForegroundColor Yellow
Write-Host "  - librosa (audio analysis library)" -ForegroundColor White
Write-Host "  - numpy (numerical computing)" -ForegroundColor White
Write-Host "  - soundfile (audio file I/O)" -ForegroundColor White
Write-Host ""

$confirmation = Read-Host "Continue with installation? (Y/N)"
if ($confirmation -ne 'Y' -and $confirmation -ne 'y') {
    Write-Host "Installation cancelled." -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "Installing audio analysis dependencies..." -ForegroundColor Green
Write-Host ""

# Install the packages
pip install librosa soundfile numpy

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Testing installation..." -ForegroundColor Yellow
python -c "import librosa; import numpy; import soundfile; print('✓ All packages imported successfully')"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Success! Audio analysis is ready to use." -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Test the functionality: python test_audio_analysis.py" -ForegroundColor White
    Write-Host "2. Pre-analyze songs: python pre_analyze_audio.py --max-files 5" -ForegroundColor White
    Write-Host "3. Start the MCP server: python mcp_server.py" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "Warning: Installation completed but packages could not be imported." -ForegroundColor Red
    Write-Host "You may need to restart your terminal or Python environment." -ForegroundColor Yellow
    Write-Host ""
}
