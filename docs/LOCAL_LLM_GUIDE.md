# Local LLM Guide - Cost-Free AI with Ollama

Run BigFlavor Band Agent with **zero API costs** using local LLMs via Ollama.

## Why Use Local LLMs?

### Pros
- ✅ **Zero API costs** - No per-token charges
- ✅ **Privacy** - Data never leaves your server
- ✅ **No rate limits** - Process as much as you want
- ✅ **Offline capable** - Works without internet (after model download)

### Cons
- ⚠️ **Lower quality** - Not as capable as Claude
- ⚠️ **Resource intensive** - Requires CPU/GPU and RAM
- ⚠️ **Slower responses** - Especially without GPU
- ⚠️ **Model management** - Need to download/update models

## Quick Start

### 1. Enable Ollama in Docker Compose

Ollama is already configured in `docker-compose.yml`. It's set to start automatically.

### 2. Download a Model

> **You usually don't need this step.** `deploy-production.sh` / `deploy-production.ps1`
> automatically pull `OLLAMA_MODEL` when `LLM_PROVIDER=ollama`. Use the script below only
> to pre-download a model before deploying, or to grab an extra model.

**Windows:**
```powershell
# Default model (qwen2.5:14b - ~9GB)
.\scripts/setup-ollama.ps1

# Or specify a different model
$env:OLLAMA_MODEL="qwen2.5:7b"
.\scripts/setup-ollama.ps1
```

**Linux/Mac:**
```bash
# Default model
chmod +x scripts/setup-ollama.sh
./scripts/setup-ollama.sh

# Or specify a different model
OLLAMA_MODEL="qwen2.5:7b" ./scripts/setup-ollama.sh
```

### 3. Configure Environment

Edit `.env.production`:
```bash
# Change this from 'anthropic' to 'ollama'
LLM_PROVIDER=ollama

# Specify your model
OLLAMA_MODEL=qwen2.5:14b

# Anthropic key now optional (but keep for fallback if desired)
ANTHROPIC_API_KEY=
```

### 4. Deploy

```bash
# Windows
.\deploy-production.ps1

# Linux/Mac
./deploy-production.sh
```

Your app now runs with zero API costs!

## Recommended Models

The agent relies heavily on **tool calling** (RAG search, radio control, etc.), so model
choice is driven by tool-calling reliability — not just chat quality. The **Qwen2.5** family
is the strongest open option here, which is why it's the default. Sizes below assume the
Q4_K_M quants Ollama pulls by default.

### On the project GPU (RTX 3090, 24GB VRAM)

| Model | ~VRAM | Speed | Tool calling | Recommendation |
|-------|-------|-------|--------------|----------------|
| `qwen2.5:7b` | ~5GB | ⚡⚡⚡ | ⭐⭐⭐ | Lighter / leaves VRAM headroom |
| `qwen2.5:14b` | ~9GB | ⚡⚡ | ⭐⭐⭐⭐ | **Recommended — best fit for 24GB** |
| `qwen2.5:32b` | ~20GB | ⚡ | ⭐⭐⭐⭐⭐ | Max quality, tight on 24GB, slower |

### Smaller / budget systems (CPU or <12GB VRAM)

| Model | Size | RAM Needed | Speed | Tool calling |
|-------|------|-----------|-------|--------------|
| `qwen2.5:3b` | ~2GB | 4GB | ⚡⚡⚡ | ⭐⭐ |
| `qwen2.5:7b` | ~4.7GB | 8GB | ⚡⚡ | ⭐⭐⭐ |
| `llama3.1:8b` | 4.7GB | 8GB | ⚡⚡ | ⭐⭐ |

## System Requirements

### Minimum (CPU Only)
- **CPU:** Modern quad-core processor
- **RAM:** 8GB (for 7-8B models)
- **Storage:** 10GB free space
- **Performance:** ~1-3 tokens/second

### Recommended (CPU)
- **CPU:** Modern 8-core processor
- **RAM:** 16GB (for 13B models)
- **Storage:** 20GB free space
- **Performance:** ~3-5 tokens/second

### Optimal (GPU)
- **GPU:** NVIDIA with 8GB+ VRAM
- **RAM:** 16GB+ system RAM
- **Storage:** 20GB free space
- **Performance:** ~20-50 tokens/second

## GPU Support (NVIDIA Only)

To enable GPU acceleration, edit `docker-compose.yml`:

```yaml
ollama:
  image: ollama/ollama:latest
  # Uncomment these lines:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

## Model Management

### List Installed Models
```bash
docker exec bigflavor-ollama ollama list
```

### Download Additional Models
```bash
# Download a specific model
docker exec bigflavor-ollama ollama pull llama3.2:3b

# Download multiple models
docker exec bigflavor-ollama ollama pull mistral:7b
docker exec bigflavor-ollama ollama pull codellama:13b
```

### Remove Models
```bash
docker exec bigflavor-ollama ollama rm llama3.1:8b
```

### Test a Model
```bash
docker exec -it bigflavor-ollama ollama run llama3.1:8b
# Type your message, then Ctrl+D to exit
```

## Switching Between Models

### Runtime Switch
Edit `.env.production`:
```bash
OLLAMA_MODEL=mistral:7b  # Change to desired model
```

Restart backend:
```bash
docker-compose restart backend
```

### Switch Between Anthropic and Ollama

**To Ollama (cost savings):**
```bash
LLM_PROVIDER=ollama
```

**Back to Anthropic (better quality):**
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

## Performance Tuning

### Optimize for Speed
Use a smaller model:
```bash
OLLAMA_MODEL=qwen2.5:7b  # Faster, lighter on VRAM
```

### Optimize for Quality
Use a larger model (requires more VRAM/RAM):
```bash
OLLAMA_MODEL=qwen2.5:32b  # Best quality (tight on a 24GB GPU)
```

### Adjust Context Window
Some models support larger context. Configure in docker-compose.yml:
```yaml
ollama:
  environment:
    - OLLAMA_NUM_PARALLEL=2
    - OLLAMA_MAX_LOADED_MODELS=1
```

## Troubleshooting

### Model Download Fails
```bash
# Check Ollama is running
docker-compose ps ollama

# View Ollama logs
docker-compose logs ollama

# Restart Ollama
docker-compose restart ollama
```

### Out of Memory Errors
- Use a smaller model (llama3.2:3b)
- Close other applications
- Add swap space on Linux
- Consider upgrading RAM

### Slow Response Times
- Enable GPU support (NVIDIA)
- Use smaller model
- Close other Docker containers
- Increase Docker Desktop memory allocation

### Backend Can't Connect to Ollama
Check network connectivity:
```bash
docker exec bigflavor-backend curl http://ollama:11434/api/tags
```

Should return list of models. If not:
```bash
# Restart both services
docker-compose restart ollama backend
```

## Cost Comparison

### Anthropic (Claude 3.5 Sonnet)
- **Input:** $3 per million tokens
- **Output:** $15 per million tokens
- **Typical chat:** ~$0.01 - $0.05 per conversation
- **Monthly cost:** $50-500+ (depending on usage)

### Ollama (Local)
- **Cost:** $0 (after initial hardware investment)
- **Electricity:** ~$5-20/month (depending on usage)
- **Hardware:** One-time cost if you need to upgrade

**Break-even:** Usually within 1-3 months for moderate usage

## Best Practices

### 1. Start Small
Begin with `llama3.2:3b` to test, then upgrade to `llama3.1:8b` if needed.

### 2. Monitor Resources
```bash
# Check memory usage
docker stats bigflavor-ollama
```

### 3. Keep Models Updated
```bash
# Update to latest version
docker exec bigflavor-ollama ollama pull llama3.1:8b
```

### 4. Hybrid Approach
Keep both configured:
- Use Ollama for high-volume, simple tasks
- Use Anthropic for complex, critical tasks
- Switch via environment variable

### 5. Backup Models
Models are stored in Docker volume `ollama_data`. Back up if needed:
```bash
docker run --rm -v bigflavor_ollama_data:/data -v $(pwd):/backup alpine tar czf /backup/ollama-backup.tar.gz /data
```

## Advanced: Custom Models

### Fine-tune for Your Use Case
```bash
# Create a custom model based on llama3.1
docker exec -it bigflavor-ollama ollama create my-music-model -f Modelfile
```

Example `Modelfile`:
```dockerfile
FROM llama3.1:8b

PARAMETER temperature 0.8
PARAMETER num_predict 2048

SYSTEM """
You are a music assistant specializing in band management and song recommendations.
You have extensive knowledge of various music genres and performance setlists.
"""
```

### Use in Production
```bash
OLLAMA_MODEL=my-music-model
```

## Model Comparison Results

Real-world testing with music queries:

| Task | Claude 3.5 | Llama 3.1 8B | Llama 3.2 3B |
|------|-----------|--------------|--------------|
| Song search | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Recommendations | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Complex queries | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Speed (CPU) | ⚡⚡⚡ | ⚡⚡ | ⚡⚡⚡ |
| Speed (GPU) | ⚡⚡⚡ | ⚡⚡⚡⚡⚡ | ⚡⚡⚡⚡⚡ |

## Support & Resources

- **Browse models:** https://ollama.com/library
- **Ollama docs:** https://github.com/ollama/ollama
- **Model benchmarks:** https://huggingface.co/spaces/lmsys/chatbot-arena-leaderboard

## Summary

For **production cost savings**, use:
```bash
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:14b
```

For **best quality**, stick with:
```bash
LLM_PROVIDER=anthropic
```

You can switch between them anytime!
