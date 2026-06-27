"""Check GPU/CUDA availability for the test."""
import torch

print("="*70)
print("GPU Configuration Check")
print("="*70)
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU Device: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
    print("\n✓ GPU acceleration will be used for Whisper models!")
else:
    print("\n⚠ No GPU detected - will use CPU (much slower)")
print("="*70)
