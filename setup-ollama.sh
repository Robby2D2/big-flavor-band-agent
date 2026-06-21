#!/bin/bash

# Ollama Model Setup Script
# Downloads and configures local LLM models for BigFlavor Band Agent

set -e

echo "=========================================="
echo "Ollama Model Setup for BigFlavor"
echo "=========================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running"
    echo "Please start Docker and try again"
    exit 1
fi

# Check if Ollama container is running
if ! docker ps | grep -q bigflavor-ollama; then
    echo "Starting Ollama container..."
    docker-compose up -d ollama
    echo "Waiting for Ollama to be ready..."
    sleep 10
fi

# Get model name from environment or use default
MODEL=${OLLAMA_MODEL:-qwen2.5:14b}

echo ""
echo "=========================================="
echo "Downloading Model: $MODEL"
echo "=========================================="
echo ""
echo "This may take several minutes depending on model size:"
echo "  - qwen2.5:7b   ~4.7GB (Lighter, good tool calling)"
echo "  - qwen2.5:14b  ~9GB   (Recommended for 24GB GPU - best tool calling)"
echo "  - qwen2.5:32b  ~20GB  (Max quality, tight on a 24GB GPU, slower)"
echo ""

# Pull the model
docker exec bigflavor-ollama ollama pull "$MODEL"

echo ""
echo "=========================================="
echo "Model Download Complete!"
echo "=========================================="
echo ""

# Test the model
echo "Testing model..."
docker exec bigflavor-ollama ollama run "$MODEL" "Say 'Hello, I am ready to help with BigFlavor!'"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Your local LLM is ready to use."
echo ""
echo "To use this model in production:"
echo "  1. Set LLM_PROVIDER=ollama in .env.production"
echo "  2. Set OLLAMA_MODEL=$MODEL in .env.production"
echo "  3. Deploy: ./deploy-production.sh"
echo ""
echo "Available models installed:"
docker exec bigflavor-ollama ollama list
echo ""
echo "To download additional models:"
echo "  docker exec bigflavor-ollama ollama pull <model-name>"
echo ""
echo "Popular models:"
echo "  - qwen2.5:7b    (Lighter, good tool calling)"
echo "  - qwen2.5:14b   (Recommended for 24GB GPU)"
echo "  - qwen2.5:32b   (Max quality, tight on 24GB)"
echo ""
echo "Browse all models: https://ollama.com/library"
echo ""
