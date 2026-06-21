#!/bin/bash

# BigFlavor Band Agent - Production Deployment Script
set -e

echo "=========================================="
echo "BigFlavor Band Agent - Production Deploy"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo -e "${RED}ERROR: .env.production file not found!${NC}"
    echo "Please copy .env.production.example to .env.production and configure it:"
    echo "  cp .env.production.example .env.production"
    echo "  nano .env.production"
    exit 1
fi

# Check if audio_library exists
if [ ! -d audio_library ]; then
    echo -e "${YELLOW}WARNING: audio_library directory not found!${NC}"
    echo "Creating empty audio_library directory..."
    mkdir -p audio_library
fi

# Load environment variables to check required ones
source .env.production

# Check critical environment variables
MISSING_VARS=0

# Database + backend trust boundary (always required in production)
if [ -z "$POSTGRES_PASSWORD" ] || [[ "$POSTGRES_PASSWORD" == *your_secure_database_password* ]]; then
    echo -e "${RED}ERROR: POSTGRES_PASSWORD not configured${NC}"
    MISSING_VARS=1
fi

if [ -z "$BACKEND_API_SECRET" ] || [[ "$BACKEND_API_SECRET" == *your_backend_api_secret* ]]; then
    echo -e "${RED}ERROR: BACKEND_API_SECRET not configured${NC}"
    echo "Generate one with: openssl rand -hex 32"
    MISSING_VARS=1
fi

# Google OAuth (frontend sign-in)
if [ -z "$GOOGLE_CLIENT_ID" ] || [[ "$GOOGLE_CLIENT_ID" == *your_google_client_id* ]]; then
    echo -e "${RED}ERROR: GOOGLE_CLIENT_ID not configured${NC}"
    MISSING_VARS=1
fi

if [ -z "$GOOGLE_CLIENT_SECRET" ] || [[ "$GOOGLE_CLIENT_SECRET" == *your_google_client_secret* ]]; then
    echo -e "${RED}ERROR: GOOGLE_CLIENT_SECRET not configured${NC}"
    MISSING_VARS=1
fi

# Anthropic key is only required when using the hosted LLM provider.
LLM_PROVIDER=${LLM_PROVIDER:-ollama}
if [ "$LLM_PROVIDER" = "anthropic" ]; then
    if [ -z "$ANTHROPIC_API_KEY" ] || [[ "$ANTHROPIC_API_KEY" == *xxxxx* ]]; then
        echo -e "${RED}ERROR: ANTHROPIC_API_KEY not configured (required when LLM_PROVIDER=anthropic)${NC}"
        MISSING_VARS=1
    fi
else
    echo -e "${GREEN}✓ LLM_PROVIDER=$LLM_PROVIDER (Anthropic key not required)${NC}"
fi

if [ $MISSING_VARS -eq 1 ]; then
    echo ""
    echo -e "${RED}Please configure all required variables in .env.production${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Environment configuration validated${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# Ask for confirmation
echo "This will:"
echo "  1. Build Docker images for all services"
echo "  2. Start services on port 80"
echo "  3. Set up the database with migrations"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo "=========================================="
echo "Building Docker images..."
echo "=========================================="
docker-compose --env-file .env.production build

echo ""
echo "=========================================="
echo "Starting services..."
echo "=========================================="
docker-compose --env-file .env.production up -d

echo ""
echo "=========================================="
echo "Waiting for services to be healthy..."
echo "=========================================="
sleep 10

# Pull the local LLM model when running with the Ollama provider.
# The model is required for the agent to work, so we download it as part of
# the deploy instead of relying on a separate manual setup step.
LLM_PROVIDER=${LLM_PROVIDER:-ollama}
if [ "$LLM_PROVIDER" = "ollama" ]; then
    OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5:14b}
    echo ""
    echo "=========================================="
    echo "Pulling Ollama model: $OLLAMA_MODEL"
    echo "=========================================="
    echo "(first run downloads several GB — this can take a while)"

    # Wait for the Ollama API to come up before pulling.
    OLLAMA_READY=0
    for i in $(seq 1 30); do
        if docker exec bigflavor-ollama ollama list > /dev/null 2>&1; then
            OLLAMA_READY=1
            break
        fi
        echo "Waiting for Ollama to be ready... ($i/30)"
        sleep 5
    done

    if [ $OLLAMA_READY -eq 0 ]; then
        echo -e "${YELLOW}WARNING: Ollama did not become ready in time.${NC}"
        echo "Pull the model manually once it is up:"
        echo "  docker exec bigflavor-ollama ollama pull $OLLAMA_MODEL"
    elif docker exec bigflavor-ollama ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
        echo -e "${GREEN}✓ Model $OLLAMA_MODEL already present${NC}"
    else
        docker exec bigflavor-ollama ollama pull "$OLLAMA_MODEL"
        echo -e "${GREEN}✓ Model $OLLAMA_MODEL ready${NC}"
    fi
fi

# Check service health
RETRIES=30
COUNT=0
while [ $COUNT -lt $RETRIES ]; do
    if docker-compose ps | grep -q "Up (healthy)"; then
        echo -e "${GREEN}✓ Services are healthy${NC}"
        break
    fi
    echo "Waiting for health checks... ($((COUNT+1))/$RETRIES)"
    sleep 5
    COUNT=$((COUNT+1))
done

if [ $COUNT -eq $RETRIES ]; then
    echo -e "${YELLOW}WARNING: Health checks taking longer than expected${NC}"
    echo "Check logs with: docker-compose logs -f"
fi

echo ""
echo "=========================================="
echo "Deployment Status"
echo "=========================================="
docker-compose ps

echo ""
echo "=========================================="
echo -e "${GREEN}Deployment Complete!${NC}"
echo "=========================================="
echo ""
echo "Your application is now running on:"
echo "  http://localhost (or your server IP)"
echo ""
echo "Useful commands:"
echo "  View logs:           docker-compose logs -f"
echo "  Stop services:       docker-compose down"
echo "  Restart service:     docker-compose restart [service]"
echo "  View this guide:     cat DOCKER_DEPLOYMENT.md"
echo ""
echo "Check service health:"
echo "  curl http://localhost/health"
echo ""
