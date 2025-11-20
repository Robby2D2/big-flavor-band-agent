# Running BigFlavor Agent Locally on Windows

There are **two ways** to run the BigFlavor Agent:

## Option 1: Simple Local Dev (Recommended for Testing)

**What you get:** Just the agent + Ollama for chatting and testing
**What you DON'T need:** Database, web frontend, Auth0, production services

### Quick Start

```powershell
# 1. Make sure Docker Desktop is running

# 2. Run this simple script:
.\run_local.ps1
```

That's it! This will:
- ✅ Start Ollama in Docker
- ✅ Download llama3.1:8b model (if needed)
- ✅ Launch an interactive chat session
- ✅ Demonstrate tool calling with Ollama
- ✅ Cost: $0.00 (completely free!)

### Manual Steps (if you prefer)

```powershell
# 1. Start Ollama
docker-compose up -d ollama

# 2. Pull model (first time only)
docker exec bigflavor-ollama ollama pull llama3.1:8b

# 3. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 4. Run the agent
python run_agent_local.py
```

---

## Option 2: Full Production Deployment

**What you get:** Complete web application with frontend, backend, database, authentication
**When to use:** When you want to deploy the full application for production use

### Requirements

1. `.env.production` file configured with:
   - Auth0 credentials (for authentication)
   - Database passwords
   - API keys
   - SSL certificates (for HTTPS)

2. Audio library folder with songs

### Steps

```powershell
# 1. Copy and configure environment
copy .env.production.example .env.production
notepad .env.production  # Configure all variables

# 2. Run deployment
.\deploy-production.ps1
```

This deploys the **full stack**:
- PostgreSQL database with pgvector
- Python FastAPI backend
- Next.js frontend
- Nginx reverse proxy
- Ollama (optional for LLM)

---

## Comparison

| Feature | Local Dev | Full Production |
|---------|-----------|-----------------|
| **Setup Time** | 2 minutes | 30+ minutes |
| **Requirements** | Docker + Python | Docker + Auth0 + SSL |
| **What Runs** | Agent + Ollama | Full web app + services |
| **Best For** | Testing, development | Production deployment |
| **Database** | Not needed | PostgreSQL required |
| **Authentication** | None | Auth0 required |
| **Web UI** | Terminal only | Full web interface |

---

## Troubleshooting Local Dev

### "Docker is not running"
- Start Docker Desktop
- Wait for it to fully start (whale icon in system tray)

### "Connection failed"
- Make sure Ollama container is running: `docker ps | findstr ollama`
- Check port is exposed: `docker port bigflavor-ollama`
- Restart Ollama: `docker-compose restart ollama`

### "Model not found"
- Download model: `docker exec bigflavor-ollama ollama pull llama3.1:8b`
- Verify: `docker exec bigflavor-ollama ollama list`

### "Python not found"
- Activate venv: `.\venv\Scripts\Activate.ps1`
- Or use full path: `.\venv\Scripts\python.exe run_agent_local.py`

---

## Next Steps

After testing locally, you can:

1. **Try different Ollama models:**
   ```powershell
   # Smaller, faster model
   docker exec bigflavor-ollama ollama pull llama3.2:3b

   # Better tool calling
   docker exec bigflavor-ollama ollama pull mistral-nemo
   ```

2. **Switch to Anthropic Claude:**
   - Edit `run_agent_local.py`
   - Change `provider="ollama"` to `provider="anthropic"`
   - Set your API key: `anthropic_api_key="sk-ant-..."`

3. **Deploy full production:**
   - Follow Option 2 above
   - Configure `.env.production`
   - Run `.\deploy-production.ps1`

---

## Cost Comparison

**Local Dev (Ollama):**
- Hardware: One-time cost (PC you already have)
- Electricity: ~$5-20/month
- Per conversation: $0.00
- **Total: FREE!**

**Anthropic Claude:**
- Input: $0.25 per million tokens (~750k words)
- Output: $1.25 per million tokens
- Per conversation: $0.001 - $0.01
- Heavy usage: $10-50/month

**Full Production Deployment:**
- Same LLM costs as above
- Plus: Server hosting (~$20-100/month)
- Plus: Database hosting (included in server)
- Plus: Domain name (~$12/year)

---

## Files Created

- `run_agent_local.py` - Simple Python chat script
- `run_local.ps1` - PowerShell launcher script
- This guide: `RUNNING_LOCALLY.md`

Enjoy your local BigFlavor Agent! 🎵
