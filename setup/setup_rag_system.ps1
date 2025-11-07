# Setup RAG System for Song Library
# This script helps you set up the audio RAG system

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Big Flavor Band - RAG System Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if virtual environment is activated
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & .\venv\Scripts\Activate.ps1
}

Write-Host "Step 1: Installing Python dependencies..." -ForegroundColor Green
Write-Host "  - PyTorch (for CLAP model)" -ForegroundColor Gray
Write-Host "  - Transformers (HuggingFace)" -ForegroundColor Gray
Write-Host "  - pgvector (PostgreSQL vector support)" -ForegroundColor Gray
Write-Host ""

# Install PyTorch with CUDA support (if you have NVIDIA GPU)
Write-Host "Do you have an NVIDIA GPU? (Y/N)" -ForegroundColor Yellow
$hasGPU = Read-Host

if ($hasGPU -eq "Y" -or $hasGPU -eq "y") {
    Write-Host "Installing PyTorch with CUDA support..." -ForegroundColor Green
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
} else {
    Write-Host "Installing PyTorch (CPU-only)..." -ForegroundColor Green
    pip install torch torchvision torchaudio
}

Write-Host "Installing other dependencies..." -ForegroundColor Green
pip install transformers pgvector
pip install -r requirements.txt

Write-Host ""
Write-Host "Step 2: Setting up database..." -ForegroundColor Green

# Check if PostgreSQL is running
$pgRunning = docker ps --filter "name=bigflavor-postgres" --filter "status=running" -q

if (-not $pgRunning) {
    Write-Host "Starting PostgreSQL container..." -ForegroundColor Yellow
    docker-compose up -d
    Start-Sleep -Seconds 5
}

Write-Host "Applying audio embeddings schema..." -ForegroundColor Green
Get-Content "sql\init\03-add-audio-embeddings.sql" | docker exec -i bigflavor-postgres psql -U bigflavor -d bigflavor

Write-Host ""
Write-Host "Step 3: Testing setup..." -ForegroundColor Green
python -c "from audio_embedding_extractor import AudioEmbeddingExtractor; print('✓ Audio embedding extractor imported successfully')"
python -c "from rag_system import SongRAGSystem; print('✓ RAG system imported successfully')"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Check indexing status:" -ForegroundColor White
Write-Host "     python index_audio_library.py status" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Index your audio library:" -ForegroundColor White
Write-Host "     python index_audio_library.py" -ForegroundColor Gray
Write-Host "     (This will take 1-10 hours depending on library size and hardware)" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Run demos:" -ForegroundColor White
Write-Host "     python demo_rag_search.py" -ForegroundColor Gray
Write-Host "     python demo_rag_search.py interactive" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Read the guide:" -ForegroundColor White
Write-Host "     RAG_SYSTEM_GUIDE.md" -ForegroundColor Gray
Write-Host ""

Write-Host "Tips:" -ForegroundColor Yellow
Write-Host "  - Start with a small subset to test (modify index_audio_library.py)" -ForegroundColor Gray
Write-Host "  - GPU highly recommended for CLAP model (10x faster)" -ForegroundColor Gray
Write-Host "  - Monitor progress in console logs" -ForegroundColor Gray
Write-Host ""
