# Docker Production Deployment Guide

This guide covers deploying BigFlavor Band Agent to production using Docker Compose on port 80.

## Architecture

```
Internet (Port 80)
    ↓
Nginx Reverse Proxy
    ↓
    ├── Frontend (Next.js) - Port 3000 (internal)
    └── Backend (FastAPI) - Port 8000 (internal)
            ↓
        PostgreSQL + pgvector - Port 5432 (internal)
```

## Prerequisites

- Docker and Docker Compose installed
- Your server's port 80 available (no other web server running)
- At least 4GB RAM recommended
- Audio files in `audio_library/` directory

## Quick Start

### 1. Set Up Environment Variables

```bash
# Copy the production environment template
cp .env.production.example .env.production

# Edit with your actual values
nano .env.production
```

Required variables:
- `POSTGRES_PASSWORD` - Secure database password
- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET` - Auth0 credentials
- `AUTH0_SECRET` - Generate with: `openssl rand -hex 32`
- `AUTH0_BASE_URL` - Your production domain (e.g., `https://yourdomain.com`)

### 2. Build and Start Services

```bash
# Build all services
docker-compose --env-file .env.production build

# Start in detached mode
docker-compose --env-file .env.production up -d

# Check status
docker-compose ps
```

### 3. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f nginx
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 4. Health Checks

```bash
# Check overall health
curl http://localhost/health

# Check backend directly
docker exec bigflavor-backend curl http://localhost:8000/health

# Check frontend directly
docker exec bigflavor-frontend curl http://localhost:3000/api/health
```

## Management Commands

### Stop Services
```bash
docker-compose down
```

### Stop and Remove Volumes (WARNING: Deletes database)
```bash
docker-compose down -v
```

### Restart a Service
```bash
docker-compose restart backend
docker-compose restart frontend
docker-compose restart nginx
```

### Rebuild After Code Changes
```bash
# Rebuild specific service
docker-compose build backend
docker-compose up -d backend

# Rebuild all
docker-compose build
docker-compose up -d
```

### Database Migrations
```bash
# Run migrations
docker exec bigflavor-backend python run_migration.py
```

### Access Logs
```bash
# Nginx access logs
docker exec bigflavor-nginx tail -f /var/log/nginx/access.log

# Nginx error logs
docker exec bigflavor-nginx tail -f /var/log/nginx/error.log
```

## Production Optimizations

### 1. Enable HTTPS (Recommended)

Add SSL certificates and update nginx configuration:

```bash
# Create SSL directory
mkdir -p nginx/ssl

# Add your certificates
# nginx/ssl/cert.pem
# nginx/ssl/key.pem

# Update docker-compose.yml to mount certificates
# See nginx documentation for SSL configuration
```

### 2. Resource Limits

Add resource limits to docker-compose.yml:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        memory: 2G
```

### 3. Backup Database

```bash
# Backup
docker exec bigflavor-postgres pg_dump -U bigflavor bigflavor > backup.sql

# Restore
docker exec -i bigflavor-postgres psql -U bigflavor bigflavor < backup.sql
```

### 4. Monitor Resource Usage

```bash
# Real-time stats
docker stats

# Disk usage
docker system df
```

## Troubleshooting

### Port 80 Already in Use
```bash
# Find what's using port 80
sudo netstat -tlnp | grep :80

# Stop conflicting service (example: apache)
sudo systemctl stop apache2
```

### Container Won't Start
```bash
# Check logs
docker-compose logs [service-name]

# Inspect container
docker inspect bigflavor-backend
```

### Database Connection Issues
```bash
# Check postgres is running
docker-compose ps postgres

# Test database connection
docker exec bigflavor-postgres psql -U bigflavor -d bigflavor -c "SELECT 1"
```

### Audio Streaming Issues
- Ensure `audio_library/` directory is mounted correctly
- Check file permissions (should be readable by container)
- Verify nginx buffering is disabled (already configured)

## Scaling

### Multiple Backend Instances

```bash
# Scale backend to 3 instances
docker-compose up -d --scale backend=3

# Nginx will automatically load balance
```

## Security Checklist

- [ ] Strong `POSTGRES_PASSWORD` set
- [ ] `AUTH0_SECRET` is random and secure (32+ characters)
- [ ] Auth0 callback URLs configured for production domain
- [ ] Firewall configured (only port 80/443 open)
- [ ] Database port 5432 not exposed publicly
- [ ] Regular backups scheduled
- [ ] HTTPS enabled with valid certificates
- [ ] Environment files (`.env.production`) not committed to git

## Updates and Maintenance

### Update Application Code
```bash
git pull
docker-compose build
docker-compose up -d
```

### Update Base Images
```bash
docker-compose pull
docker-compose up -d
```

### Clean Up Old Images
```bash
docker image prune -a
```

## Support

- Check logs: `docker-compose logs -f`
- Restart services: `docker-compose restart`
- Full reset: `docker-compose down && docker-compose up -d`
