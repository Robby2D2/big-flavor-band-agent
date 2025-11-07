# 🎸 Claude 3 Haiku Agent Setup Guide

## Overview

Your Big Flavor Band agent now supports **Claude 3 Haiku**, the most cost-effective Claude model!

- **Cost**: ~$0.25/MTok input, ~$1.25/MTok output
- **Speed**: Fast responses
- **Quality**: Smart enough for music recommendations
- **MCP Ready**: Works with your RAG-powered MCP server

## 🚀 Quick Start

### 1. Install Anthropic SDK

```powershell
# Activate your virtual environment
.\venv\Scripts\Activate.ps1

# Install the anthropic package
pip install anthropic
```

### 2. Get Your API Key

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to "API Keys"
4. Create a new API key
5. Copy your key (starts with `sk-ant-...`)

### 3. Set Environment Variable

**Windows PowerShell:**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

**To make it permanent:**
```powershell
[System.Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', 'sk-ant-your-key-here', 'User')
```

**Linux/Mac:**
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Add to ~/.bashrc or ~/.zshrc to make permanent
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.bashrc
```

### 4. Run the Agent!

**Interactive Mode** (Chat with Claude):
```powershell
python claude_agent.py
```

**Example Mode** (See pre-built examples):
```powershell
python claude_agent.py example
```

## 💬 Usage Examples

### Interactive Chat
```
You: Find me upbeat rock songs around 120 BPM

🤖 Agent: I'll help you find upbeat rock songs around 120 BPM from the Big Flavor 
         Band catalog! Let me search for songs with that tempo and high energy...
         
         [Claude's response with recommendations]

💡 Tokens: 450 | Cost: $0.0008
```

### Programmatic Usage

```python
import asyncio
from claude_agent import ClaudeMusicAgent

async def find_songs():
    # Initialize agent
    agent = ClaudeMusicAgent()
    
    # Find similar songs
    result = await agent.discover_similar_songs(
        "songs like Summer Groove",
        limit=5
    )
    
    print(result["response"])
    print(f"Cost: ${result['cost_estimate']['total_cost_usd']:.4f}")
    
    # Create a playlist
    result = await agent.create_playlist(
        "chill afternoon vibes",
        song_count=10
    )
    
    print(result["response"])
    
    # Show cost summary
    agent.print_cost_summary()

asyncio.run(find_songs())
```

## 💰 Cost Tracking

The agent automatically tracks token usage and estimates costs:

```python
# Get session statistics
stats = agent.get_session_stats()
print(f"Total cost: ${stats['cost_estimate']['total_cost_usd']:.4f}")

# Print detailed cost summary
agent.print_cost_summary()
```

**Example Output:**
```
============================================================
💰 Claude API Cost Summary
============================================================
Model: claude-3-haiku-20240307
Total Tokens: 1,250
  - Input:  850 tokens
  - Output: 400 tokens

Estimated Cost: $0.0007
  - Input:  $0.0002
  - Output: $0.0005
============================================================
```

## 🎯 Available Commands

### Interactive Mode Commands:
- **Your question** - Ask Claude anything about the music library
- **`cost`** - Show current session costs
- **`reset`** - Reset conversation history
- **`quit`** - Exit and show final cost summary

### Example Queries:
```
"Find me songs that sound like classic rock"
"Create a 10-song playlist for a dinner party"
"What songs have a tempo around 130 BPM?"
"Recommend energetic songs for a workout"
"Find songs similar to 'Summer Groove'"
```

## 🔧 API Reference

### ClaudeMusicAgent

```python
class ClaudeMusicAgent:
    def __init__(self, api_key: Optional[str] = None)
    
    async def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7
    ) -> Dict[str, Any]
    
    async def discover_similar_songs(
        self,
        song_query: str,
        limit: int = 5
    ) -> Dict[str, Any]
    
    async def create_playlist(
        self,
        theme: str,
        song_count: int = 10
    ) -> Dict[str, Any]
    
    def get_session_stats(self) -> Dict[str, Any]
    def print_cost_summary(self)
    def reset_conversation(self)
```

## 📊 Cost Estimates

### Claude 3 Haiku Pricing
- **Input**: $0.25 per million tokens (~750,000 words)
- **Output**: $1.25 per million tokens (~750,000 words)

### Typical Usage Costs:
| Task | Est. Tokens | Est. Cost |
|------|-------------|-----------|
| Simple query | 200-500 | $0.0002-$0.0007 |
| Song recommendations | 500-1000 | $0.0005-$0.0015 |
| Playlist creation | 1000-2000 | $0.0015-$0.0030 |
| Long conversation (10 msgs) | 5000-10000 | $0.0075-$0.0150 |

**Example**: 1,000 queries = ~$0.50-$1.50

## 🎨 Customization

### Change Model
```python
agent = ClaudeMusicAgent()
agent.model = "claude-3-5-haiku-20241022"  # Newer Haiku
# or
agent.model = "claude-3-5-sonnet-20241022"  # Higher quality
```

### Custom System Prompt
```python
custom_prompt = """You are a DJ expert specializing in party music..."""

result = await agent.chat(
    "Find dance songs",
    system_prompt=custom_prompt
)
```

### Adjust Temperature
```python
# More focused/deterministic (0.0-0.5)
result = await agent.chat("Find songs", temperature=0.3)

# More creative/varied (0.7-1.0)
result = await agent.chat("Create playlist", temperature=0.9)
```

## 🔗 Next Steps: Connect to MCP Server

**Current**: Claude agent is standalone (no MCP tools yet)  
**Next**: Integrate with your RAG-powered MCP server

To enable MCP tools, we'll need to:
1. Add MCP client functionality to `claude_agent.py`
2. Connect to your running MCP server
3. Give Claude access to semantic search tools

Want me to integrate the MCP server now so Claude can use your RAG search tools?

## 🐛 Troubleshooting

### "ANTHROPIC_API_KEY environment variable not set"
**Solution**: Set your API key:
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

### "Invalid API key"
**Solution**: 
- Check your key starts with `sk-ant-`
- Verify it's active at https://console.anthropic.com/
- Make sure there are no extra spaces

### "Rate limit exceeded"
**Solution**: 
- Claude 3 Haiku has generous rate limits
- Wait a moment and retry
- Check your usage at https://console.anthropic.com/

### Module not found: anthropic
**Solution**:
```powershell
pip install anthropic
```

## 📚 Related Files

- `claude_agent.py` - Claude 3 Haiku agent implementation
- `mcp_server.py` - RAG-powered MCP server
- `rag_system.py` - Semantic search system
- `requirements.txt` - Updated with anthropic package

## 🎉 What You Can Do Now

✅ **Chat with Claude** about your music library  
✅ **Get recommendations** based on natural language  
✅ **Create playlists** for any theme or mood  
✅ **Track costs** automatically  
✅ **Low cost** - ~$0.50-$1.50 per 1000 queries  

---

**Ready to try it?**
```powershell
python claude_agent.py
```
