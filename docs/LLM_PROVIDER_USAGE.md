# LLM Provider Usage Guide

The BigFlavorAgent now supports multiple LLM providers with full tool calling capabilities!

## Supported Providers

### 1. Anthropic Claude (Cloud)
- **Cost**: Pay-per-use API ($0.25/M input tokens, $1.25/M output tokens)
- **Quality**: Excellent
- **Speed**: Fast (cloud-based)
- **Tool Calling**: ✅ Native support

### 2. Ollama (Local)
- **Cost**: Free (one-time hardware cost + electricity)
- **Quality**: Good to Excellent (model dependent)
- **Speed**: Depends on hardware
- **Tool Calling**: ✅ Native support (v0.3.0+)

---

## Quick Start

### Using Anthropic (Default)

```python
from big_flavor_agent import BigFlavorAgent

# Option 1: Use environment variable
# Set ANTHROPIC_API_KEY in .env file
agent = BigFlavorAgent()

# Option 2: Pass API key directly
agent = BigFlavorAgent(api_key="sk-ant-...")

await agent.initialize()
result = await agent.chat("Find me some upbeat songs")
print(result["response"])
```

### Using Ollama (Local)

```python
from big_flavor_agent import BigFlavorAgent

# Option 1: Use environment variables
# Set in .env:
#   LLM_PROVIDER=ollama
#   OLLAMA_BASE_URL=http://localhost:11434
#   OLLAMA_MODEL=llama3.1:8b
agent = BigFlavorAgent()

# Option 2: Pass configuration directly
agent = BigFlavorAgent(
    llm_provider="ollama",
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.1:8b"
)

await agent.initialize()
result = await agent.chat("Find me some upbeat songs")
print(result["response"])
```

---

## Environment Configuration

### .env for Anthropic
```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx
```

### .env for Ollama
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### .env.production for Docker
```bash
# For Ollama in Docker
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434  # Docker service name
OLLAMA_MODEL=llama3.1:8b
```

---

## Ollama Model Recommendations

### Best Models for Tool Calling

| Model | Size | RAM | Quality | Speed | Notes |
|-------|------|-----|---------|-------|-------|
| **llama3.1:8b** | 4.7GB | 8GB | ⭐⭐⭐⭐ | ⚡⚡⚡ | **Recommended** - Best balance |
| **mistral-nemo** | 7GB | 12GB | ⭐⭐⭐⭐⭐ | ⚡⚡ | Excellent tool calling |
| **qwen2.5:7b** | 4.7GB | 8GB | ⭐⭐⭐⭐ | ⚡⚡⚡ | Strong tool calling |
| **firefunction-v2** | 7GB | 12GB | ⭐⭐⭐⭐⭐ | ⚡⚡ | Fine-tuned for functions |
| **llama3.2:3b** | 2GB | 4GB | ⭐⭐⭐ | ⚡⚡⚡⚡ | Budget option |
| **command-r-plus** | 104GB | 128GB | ⭐⭐⭐⭐⭐ | ⚡ | Best quality, huge size |

### How to Download Models

```bash
# Pull a model
ollama pull llama3.1:8b

# List installed models
ollama list

# Test a model
ollama run llama3.1:8b "Hello!"
```

---

## Setup Ollama

### Windows
```powershell
# Install Ollama
winget install Ollama.Ollama

# Or download from https://ollama.com/download

# Pull recommended model
ollama pull llama3.1:8b

# Start Ollama (usually auto-starts)
# Check it's running: http://localhost:11434
```

### Linux/Mac
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull recommended model
ollama pull llama3.1:8b

# Ollama runs as a service automatically
```

### Docker (Production)
```bash
# Already configured in docker-compose.yml
docker-compose up -d ollama

# Pull model inside container
docker exec bigflavor-ollama ollama pull llama3.1:8b

# Or use setup script
.\setup-ollama.ps1  # Windows
./setup-ollama.sh   # Linux/Mac
```

---

## Tool Calling Support

Both providers support **full tool calling** with automatic format conversion!

### How It Works

The LLM provider abstraction automatically:
1. Converts tool definitions from Anthropic format → Ollama format
2. Sends requests to the appropriate API
3. Converts responses back to a unified format
4. Handles multi-turn tool use conversations

### Example: Tool Use with Either Provider

```python
# This code works IDENTICALLY with both Anthropic and Ollama!

agent = BigFlavorAgent()  # Uses LLM_PROVIDER from .env
await agent.initialize()

# Agent will automatically use tools to search
result = await agent.chat("Find songs that sound like Going to California")

# Behind the scenes:
# 1. LLM receives tools: search_by_text, find_song_by_title, etc.
# 2. LLM decides to call find_song_by_title("Going to California")
# 3. Provider executes the tool
# 4. Provider sends results back to LLM
# 5. LLM uses results to answer user
```

---

## Cost Comparison

### Anthropic Claude
- **Input**: $0.25 per million tokens (~750k words)
- **Output**: $1.25 per million tokens (~750k words)
- **Typical conversation**: $0.001 - $0.01
- **Heavy usage**: $10-50/month

### Ollama (Local)
- **Initial**: Hardware cost (GPU recommended but optional)
- **Ongoing**: Electricity (~$5-20/month depending on usage)
- **Per conversation**: $0.00
- **Unlimited usage**: Same monthly cost

### Break-even Analysis
- Light usage (<1000 requests/month): Anthropic cheaper
- Heavy usage (>10,000 requests/month): Ollama cheaper
- Privacy-focused: Ollama (data stays local)
- Zero-latency required: Anthropic (faster response)

---

## Performance Tips

### For Ollama

**Faster Responses:**
- Use smaller models (llama3.2:3b)
- Use GPU acceleration if available
- Reduce max_tokens parameter
- Keep model in memory (don't stop Ollama)

**Better Quality:**
- Use larger models (mistral-nemo, qwen2.5:14b)
- Increase temperature for creativity
- Use fine-tuned models (firefunction-v2)

**Enable GPU (NVIDIA):**
```yaml
# In docker-compose.yml
ollama:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### For Anthropic

**Reduce Costs:**
- Use smaller context windows
- Cache system prompts (coming soon)
- Batch requests when possible
- Use streaming for better UX

**Faster Responses:**
- Use streaming
- Reduce max_tokens
- Simplify system prompts

---

## Switching Providers

You can switch between providers **without changing any code**:

### Method 1: Environment Variable
```bash
# .env
LLM_PROVIDER=anthropic  # or 'ollama'
```

### Method 2: Runtime
```python
# Anthropic
agent = BigFlavorAgent(llm_provider="anthropic", api_key="...")

# Ollama
agent = BigFlavorAgent(
    llm_provider="ollama",
    ollama_model="llama3.1:8b"
)
```

---

## Troubleshooting

### Ollama Connection Issues

**Error: Connection refused**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve  # Linux/Mac
# Windows: Should auto-start, check system tray
```

**Error: Model not found**
```bash
# Pull the model
ollama pull llama3.1:8b

# Verify it's installed
ollama list
```

### Tool Calling Issues

**Ollama not calling tools:**
- Ensure model supports tool calling (check model page on ollama.com)
- Try a different model (llama3.1, mistral-nemo recommended)
- Check Ollama version (needs v0.3.0+): `ollama --version`

**Tools not working correctly:**
- Check tool definitions in `big_flavor_agent.py`
- Verify tool implementation in `_call_tool()`
- Enable debug logging to see tool calls

---

## Best Practices

### Development
- Use **Anthropic** for faster iteration
- Use **Ollama** for testing without API costs
- Test on both providers before deployment

### Production
- Use **Anthropic** for low-volume, high-reliability needs
- Use **Ollama** for high-volume, cost-sensitive deployments
- Use **Ollama** for privacy/security-sensitive applications
- Consider hybrid: Anthropic for complex queries, Ollama for simple ones

### Quality Assurance
- Test critical features on both providers
- Monitor response quality differences
- Have fallback from Ollama → Anthropic for failures
- Log which provider handled each request

---

## Advanced: Custom LLM Providers

You can add support for other providers by:

1. Extending the `LLMProvider` base class
2. Implementing required methods:
   - `generate_response()`
   - `generate_stream()`
   - `supports_tool_calling()`
   - `generate_with_tools()`
3. Adding format converters if needed
4. Registering in `get_llm_provider()` factory

Example providers you could add:
- OpenAI GPT-4
- Google Gemini
- Cohere Command R+
- Azure OpenAI
- AWS Bedrock

---

## FAQ

**Q: Can I use both providers in the same application?**
A: Yes! Create separate agent instances with different providers.

**Q: Which provider is better?**
A: Anthropic for quality and speed, Ollama for cost and privacy. Both support full tool calling.

**Q: Can I switch providers mid-conversation?**
A: Not recommended - conversation history format may differ. Start fresh conversations.

**Q: Does Ollama work offline?**
A: Yes! Once models are downloaded, Ollama works completely offline.

**Q: How do I know which provider is being used?**
A: Check the logs on agent initialization, or check `type(agent.llm_provider)`.

**Q: Can I use Ollama with cloud deployment?**
A: Yes, but you need to run Ollama on a server with sufficient resources (GPU recommended).

---

## Next Steps

1. **Try both providers** - See which works best for your use case
2. **Benchmark performance** - Compare speed, quality, and cost
3. **Read the Ollama guide** - See `docs/LOCAL_LLM_GUIDE.md`
4. **Experiment with models** - Try different Ollama models
5. **Monitor costs** - Track API usage with Anthropic

Happy coding! 🎵
