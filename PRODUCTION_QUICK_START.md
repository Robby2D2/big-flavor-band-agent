# Production Quick Start - Docker on Port 80

Everything you need to deploy BigFlavor Band Agent to production using Docker Compose.

## What You Got

Your application now runs as 5 Docker containers:
1. **Nginx** (port 80) - Routes traffic to frontend and backend
2. **Next.js Frontend** (internal port 3000) - User interface
3. **FastAPI Backend** (internal port 8000) - API and radio stream
4. **PostgreSQL** (internal port 5432) - Database with pgvector
5. **Ollama** (optional, internal port 11434) - Local LLM for zero-cost AI

## Files Created

### Docker Configuration
- `Dockerfile.backend` - Python/FastAPI container
- `Dockerfile.frontend` - Next.js container
- `docker-compose.yml` - Orchestrates all services
- `.dockerignore` - Excludes unnecessary files from builds

### Nginx
- `nginx/nginx.conf` - Reverse proxy configuration
  - Routes `/` to frontend
  - Routes `/api/*` to backend
  - Optimized for audio streaming (buffering disabled)

### Deployment
- `.env.production.example` - Template for environment variables
- `deploy-production.sh` - Linux/Mac deployment script
- `deploy-production.ps1` - Windows deployment script
- `DOCKER_DEPLOYMENT.md` - Complete deployment guide

### Local LLM (Cost Savings)
- `setup-ollama.sh` - Linux/Mac Ollama model downloader
- `setup-ollama.ps1` - Windows Ollama model downloader
- `LOCAL_LLM_GUIDE.md` - Complete guide for local LLM usage
- `src/llm/llm_provider.py` - LLM abstraction layer (supports Anthropic + Ollama)

### Health Checks
- `frontend/app/api/health/route.ts` - Frontend health endpoint

## Deploy to Production (6 Steps)

### 1. Configure Environment
```bash
# Copy template
cp .env.production.example .env.production

# Edit with your values
nano .env.production
```

**Required variables:**
- `LLM_PROVIDER` - Choose `anthropic` or `ollama` (for cost savings)
- `ANTHROPIC_API_KEY` - Your API key (only if using `anthropic`)
- `OLLAMA_MODEL` - Model to use (only if using `ollama`, default: `llama3.1:8b`)
- `AUTH0_SECRET` - Generate: `openssl rand -hex 32`
- `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` - From Auth0 dashboard
- `AUTH0_BASE_URL` - Your production URL
- `POSTGRES_PASSWORD` - Strong database password

**💰 Cost Savings with Local LLM:**
Set `LLM_PROVIDER=ollama` to use free local AI instead of paid Anthropic API.
See `LOCAL_LLM_GUIDE.md` for full details on model selection and setup.

### 2. Setup Local LLM (Optional - For Cost Savings)

If using `LLM_PROVIDER=ollama`, download models first:

**Windows:**
```powershell
.\setup-ollama.ps1
```

**Linux/Mac:**
```bash
chmod +x setup-ollama.sh
./setup-ollama.sh
```

This downloads the AI model (~4.7GB for llama3.1:8b). See `LOCAL_LLM_GUIDE.md` for model options.

### 3. Ensure Audio Files
```bash
# Your MP3 files should be in:
ls audio_library/
# Example: 1_Song_Title.mp3, 2_Another_Song.mp3
```

### 4. Run Deployment Script

**Linux/Mac:**
```bash
chmod +x deploy-production.sh
./deploy-production.sh
```

**Windows:**
```powershell
.\deploy-production.ps1
```

**Or manually:**
```bash
docker-compose --env-file .env.production build
docker-compose --env-file .env.production up -d
```

### 5. Verify Deployment
```bash
# Check all services running
docker-compose ps

# Test health
curl http://localhost/health

# View logs
docker-compose logs -f
```

### 6. Access Your Application
Open browser to: `http://your-server-ip` or `http://localhost`

## Common Commands

```bash
# View logs
docker-compose logs -f                    # All services
docker-compose logs -f backend            # Just backend
docker-compose logs -f nginx              # Just nginx

# Restart a service
docker-compose restart backend

# Stop everything
docker-compose down

# Rebuild after code changes
docker-compose build backend
docker-compose up -d backend

# Check resource usage
docker stats

# Backup database
docker exec bigflavor-postgres pg_dump -U bigflavor bigflavor > backup.sql
```

## Architecture Flow

```
User Request to http://your-server:80
    ↓
Nginx Container (port 80)
    ↓
    ├─→ Request to /
    │   └→ Frontend Container (Next.js on port 3000)
    │       └→ Renders UI, handles Auth0 login
    │
    └─→ Request to /api/*
        └→ Backend Container (FastAPI on port 8000)
            ├→ /api/radio/* - Audio streaming
            ├→ /api/search - RAG search
            └→ /api/agent/chat - AI agent
                └→ PostgreSQL Container (port 5432)
                    └→ Vector embeddings + song data
```

## Environment Variables Explained

| Variable | Purpose | Example |
|----------|---------|---------|
| `LLM_PROVIDER` | AI provider choice | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | Claude API access (if using anthropic) | `sk-ant-api03-...` |
| `OLLAMA_MODEL` | Local model name (if using ollama) | `llama3.1:8b` |
| `OLLAMA_BASE_URL` | Ollama service URL | `http://ollama:11434` |
| `POSTGRES_PASSWORD` | Database password | `super_secure_pass_123` |
| `AUTH0_DOMAIN` | Auth0 tenant | `yourapp.us.auth0.com` |
| `AUTH0_CLIENT_ID` | Auth0 app ID | `abc123...` |
| `AUTH0_CLIENT_SECRET` | Auth0 app secret | `xyz789...` |
| `AUTH0_SECRET` | Session encryption | 64-char random string |
| `AUTH0_BASE_URL` | Your app URL | `https://yourdomain.com` |
| `AUTH0_ISSUER_BASE_URL` | Auth0 issuer | `https://yourapp.us.auth0.com` |

## Troubleshooting

### Port 80 in use
```bash
# Windows
netstat -ano | findstr :80
taskkill /F /PID <PID>

# Linux
sudo netstat -tlnp | grep :80
sudo systemctl stop apache2  # or whatever is using it
```

### Can't connect to database
```bash
# Check postgres is healthy
docker-compose ps postgres

# View postgres logs
docker-compose logs postgres

# Test connection
docker exec bigflavor-postgres psql -U bigflavor -c "SELECT 1"
```

### Audio not streaming
1. Check audio_library is mounted: `docker-compose ps backend`
2. Verify file permissions: Files should be readable
3. Check nginx logs: `docker-compose logs nginx`

### Health checks failing
```bash
# Test each service
curl http://localhost/health                    # Nginx
docker exec bigflavor-frontend curl http://localhost:3000/api/health
docker exec bigflavor-backend curl http://localhost:8000/health
```

### Ollama / Local LLM issues
```bash
# Check Ollama is running
docker-compose ps ollama

# View Ollama logs
docker-compose logs ollama

# List downloaded models
docker exec bigflavor-ollama ollama list

# Test model directly
docker exec bigflavor-ollama ollama run llama3.1:8b "Hello"

# Restart Ollama
docker-compose restart ollama
```

For more Ollama troubleshooting, see `LOCAL_LLM_GUIDE.md`

## Security Notes

✅ **Implemented:**
- Services isolated in Docker network
- Database not exposed publicly
- Nginx security headers enabled
- Audio files mounted read-only

⚠️ **To Add:**
- HTTPS/SSL certificates (see DOCKER_DEPLOYMENT.md)
- Firewall rules (only 80/443 open)
- Rate limiting
- Regular security updates

## Next Steps

1. **Enable HTTPS** - Add SSL certificates to nginx
2. **Set up backups** - Schedule database dumps
3. **Configure monitoring** - Add logging/metrics
4. **Update Auth0** - Add production callback URLs
5. **Test failover** - Ensure containers restart on failure

## Need Help?

- Full guide: `cat DOCKER_DEPLOYMENT.md`
- Check logs: `docker-compose logs -f`
- Status: `docker-compose ps`
- Stats: `docker stats`

---

**Your production stack is ready! 🚀**
