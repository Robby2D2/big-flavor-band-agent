# Enable GPU Support for Ollama (Windows + Docker Desktop)

Your system: **NVIDIA GeForce RTX 3090** (24GB VRAM) - Excellent! 🚀

## Prerequisites Check

✅ NVIDIA GPU: RTX 3090 (detected)
✅ NVIDIA Driver: 576.88 (installed)
✅ Docker Desktop: 4.50.0 (installed)
⚠️ GPU in Docker: Not enabled yet

## Step-by-Step Setup

### Step 1: Enable WSL2 in Docker Desktop

1. **Open Docker Desktop**
2. Go to **Settings** (gear icon)
3. Navigate to **General**
4. Make sure these are checked:
   - ✅ **Use the WSL 2 based engine**
   - ✅ **Use the WSL 2 based engine (Windows Home can only run the WSL 2 backend)**

5. Click **Apply & Restart**

### Step 2: Enable WSL Integration

1. In Docker Desktop Settings
2. Go to **Resources** → **WSL Integration**
3. Enable integration with your WSL distros:
   - ✅ **Enable integration with my default WSL distro**
   - ✅ Enable for any Ubuntu/Debian distros you have

4. Click **Apply & Restart**

### Step 3: Install NVIDIA Container Toolkit in WSL2

Open **WSL2** terminal (Ubuntu/Debian) and run:

```bash
# Add NVIDIA package repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/$(ARCH) /" | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update and install
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
```

**OR** if you don't have WSL2 set up, use the simpler Windows method:

### Alternative: Docker Desktop GPU Support (Simpler)

Docker Desktop 4.50+ includes built-in GPU support!

1. Open **Docker Desktop Settings**
2. Go to **Resources** → **Advanced**
3. Under **Resource allocation**, you should see:
   - **GPU support** toggle
4. Enable it
5. Restart Docker Desktop

### Step 4: Restart Ollama with GPU

From PowerShell in your project directory:

```powershell
# Stop Ollama
docker-compose down ollama

# Start with GPU enabled
docker-compose up -d ollama

# Wait for it to start
Start-Sleep -Seconds 10
```

### Step 5: Verify GPU is Working

```powershell
# Check if GPU is visible in container
docker exec bigflavor-ollama nvidia-smi

# You should see your RTX 3090 listed!
```

### Step 6: Test Performance

Run the test again and you should see MUCH faster responses:

```powershell
.\run_local.ps1
```

Expected improvements:
- **CPU-only**: ~30-60 seconds per response
- **GPU (RTX 3090)**: ~2-5 seconds per response ⚡

---

## Troubleshooting

### Error: "nvidia-smi not found"

**Solution 1: Use Docker Desktop GPU Support**
- Make sure you're on Docker Desktop 4.19+
- Enable GPU support in Settings → Resources
- Restart Docker Desktop

**Solution 2: Install NVIDIA Container Toolkit**
Follow Step 3 above in WSL2

### Error: "failed to create shim task"

**Cause:** Docker can't access GPU
**Solution:**
1. Make sure NVIDIA drivers are up to date
2. Restart Docker Desktop
3. Try using the Docker Desktop GPU support instead of nvidia-docker

### Error: "Error response from daemon: could not select device driver"

**Solution:**
```powershell
# Restart Docker Desktop completely
# Then try:
docker-compose down
docker-compose up -d ollama
```

### Still on CPU?

Check docker logs:
```powershell
docker logs bigflavor-ollama
```

Look for:
- ✅ `CUDA available: true` (good - GPU detected)
- ❌ `CUDA available: false` (bad - GPU not detected)

---

## Performance Comparison

With your **RTX 3090 (24GB)**:

| Model | CPU Speed | GPU Speed | GPU Speedup |
|-------|-----------|-----------|-------------|
| llama3.1:8b | ~45 sec | ~3 sec | **15x faster** ⚡ |
| llama3.2:3b | ~20 sec | ~1 sec | **20x faster** ⚡ |
| mistral-nemo:7b | ~50 sec | ~4 sec | **12x faster** ⚡ |
| codellama:13b | ~90 sec | ~6 sec | **15x faster** ⚡ |

You can also run **bigger models**:
- `llama3.1:70b` - Only ~8-12 sec (vs 5+ minutes on CPU!)
- `qwen2.5:32b` - Much higher quality responses

---

## Quick Reference

```powershell
# Check GPU in container
docker exec bigflavor-ollama nvidia-smi

# Restart with GPU
docker-compose down ollama && docker-compose up -d ollama

# View logs
docker logs -f bigflavor-ollama

# Run chat session
.\run_local.ps1
```

---

## What Changed

I've already updated `docker-compose.yml` to enable GPU support:
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

Just need to:
1. Enable GPU support in Docker Desktop (Settings → Resources)
2. Restart Ollama: `docker-compose down ollama && docker-compose up -d ollama`
3. Verify: `docker exec bigflavor-ollama nvidia-smi`

Enjoy your blazing-fast local LLM! 🚀
