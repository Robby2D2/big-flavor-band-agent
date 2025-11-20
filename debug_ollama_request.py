"""
Debug script to see what's being sent to Ollama and why it's returning 400
"""
import asyncio
import json
import httpx


async def test_ollama_direct():
    """Test Ollama API directly to see what works"""

    print("Testing Ollama API directly...")
    print()

    client = httpx.AsyncClient(timeout=30.0)

    # Test 1: Simple request without tools
    print("=" * 70)
    print("Test 1: Simple request (no tools)")
    print("=" * 70)

    payload1 = {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "user", "content": "Say hello"}
        ],
        "stream": False
    }

    print(f"Payload:\n{json.dumps(payload1, indent=2)}")
    print()

    try:
        response = await client.post("http://localhost:11434/api/chat", json=payload1)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {result.get('message', {}).get('content', '')[:100]}")
            print("[OK] Simple request works!")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

    print()

    # Test 2: Request with tools (Ollama format)
    print("=" * 70)
    print("Test 2: Request with tools (Ollama format)")
    print("=" * 70)

    payload2 = {
        "model": "llama3.1:8b",
        "messages": [
            {"role": "user", "content": "What is 5 + 3?"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"}
                        },
                        "required": ["a", "b"]
                    }
                }
            }
        ],
        "stream": False
    }

    print(f"Payload:\n{json.dumps(payload2, indent=2)}")
    print()

    try:
        response = await client.post("http://localhost:11434/api/chat", json=payload2)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Response:\n{json.dumps(result.get('message', {}), indent=2)}")
            print("[OK] Tool request works!")
        else:
            print(f"Error response:")
            print(response.text)
            print()
            print("[FAIL] Tool request failed with 400")
            print()
            print("This might mean:")
            print("  1. Ollama version doesn't support tools")
            print("  2. Model doesn't support tools")
            print("  3. Tool format is incorrect")
    except Exception as e:
        print(f"Error: {e}")

    print()

    # Test 3: Check Ollama version
    print("=" * 70)
    print("Test 3: Ollama version info")
    print("=" * 70)

    try:
        response = await client.get("http://localhost:11434/api/version")
        if response.status_code == 200:
            version = response.json()
            print(f"Ollama version: {version.get('version', 'unknown')}")
        else:
            response = await client.get("http://localhost:11434/api/tags")
            if response.status_code == 200:
                print("Ollama is running (version endpoint not available)")
    except Exception as e:
        print(f"Could not get version: {e}")

    print()

    # Test 4: Check if model has "tools" capability
    print("=" * 70)
    print("Test 4: Model information")
    print("=" * 70)

    try:
        response = await client.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            tags = response.json()
            models = tags.get('models', [])
            for model in models:
                if 'llama3.1:8b' in model.get('name', ''):
                    print(f"Model: {model.get('name')}")
                    print(f"Size: {model.get('size', 0) / 1e9:.1f} GB")
                    print(f"Modified: {model.get('modified_at', 'unknown')}")

                    # Check details
                    details = model.get('details', {})
                    if details:
                        print(f"Details: {json.dumps(details, indent=2)}")
    except Exception as e:
        print(f"Could not get model info: {e}")

    await client.aclose()

    print()
    print("=" * 70)
    print("Diagnosis")
    print("=" * 70)
    print()
    print("If Test 1 passed but Test 2 failed with 400:")
    print("  - Ollama version may not support tool calling")
    print("  - You need Ollama v0.3.0 or later")
    print("  - Model must support tool calling (llama3.1 should)")
    print()
    print("To check Ollama version in container:")
    print("  docker exec bigflavor-ollama ollama --version")
    print()
    print("To update Ollama:")
    print("  docker-compose pull ollama")
    print("  docker-compose up -d ollama")
    print()


if __name__ == "__main__":
    asyncio.run(test_ollama_direct())
