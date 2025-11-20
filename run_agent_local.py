"""
Simple local runner for BigFlavorAgent with Ollama
No Docker, database, or web services required - just the agent!
"""
import asyncio
import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src" / "agent"))
sys.path.insert(0, str(project_root / "src" / "llm"))

from llm_provider import get_llm_provider


async def simple_chat_session():
    """Run a simple chat session with Ollama (no database needed)"""

    print("=" * 70)
    print("BigFlavor Agent - Local Chat (Ollama)")
    print("=" * 70)
    print()
    print("This is a simplified version that doesn't need the database.")
    print("It just demonstrates tool calling with Ollama.")
    print()
    print("Commands:")
    print("  - Type your message and press Enter")
    print("  - Type 'quit' to exit")
    print()
    print("=" * 70)
    print()

    # Create Ollama provider
    print("Connecting to Ollama...")
    provider = get_llm_provider(
        provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1:8b"
    )
    print(f"Connected to {provider.model} at {provider.base_url}")
    print()

    # Define some simple tools for demonstration
    tools = [
        {
            "name": "calculate",
            "description": "Perform a mathematical calculation",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to calculate (e.g., '2 + 2', '10 * 5')"
                    }
                },
                "required": ["expression"]
            }
        },
        {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    ]

    conversation = []
    system_prompt = """You are a helpful AI assistant. You have access to tools to help answer questions.
When asked to do math, use the calculate tool.
When asked about weather, use the get_weather tool.
Be concise and friendly."""

    # Chat loop
    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break

            # Add to conversation
            conversation.append({
                "role": "user",
                "content": user_input
            })

            # Get response from Ollama with tools
            print("\nAssistant: ", end="", flush=True)

            response = await provider.generate_with_tools(
                messages=conversation,
                tools=tools,
                system=system_prompt,
                max_tokens=2048,
                temperature=0.7
            )

            # Check if tools were called
            tool_calls = []
            text_response = ""

            for block in response["content"]:
                block_type = block.get("type") if isinstance(block, dict) else block.type

                if block_type == "tool_use":
                    tool_name = block.get("name") if isinstance(block, dict) else block.name
                    tool_input = block.get("input") if isinstance(block, dict) else block.input
                    tool_calls.append((tool_name, tool_input))
                elif block_type == "text":
                    text = block.get("text") if isinstance(block, dict) else block.text
                    text_response += text

            # If tools were called, simulate responses
            if tool_calls:
                print(f"[Calling tools: {', '.join(t[0] for t in tool_calls)}]")

                # Add assistant response with tool use
                conversation.append({
                    "role": "assistant",
                    "content": response["content"]
                })

                # Simulate tool results
                tool_results = []
                for tool_name, tool_input in tool_calls:
                    if tool_name == "calculate":
                        try:
                            result = eval(tool_input["expression"])
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": f"tool_{tool_name}",
                                "content": f"Result: {result}"
                            })
                        except:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": f"tool_{tool_name}",
                                "content": "Error: Invalid expression"
                            })
                    elif tool_name == "get_weather":
                        # Simulated weather data
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": f"tool_{tool_name}",
                            "content": f"Weather in {tool_input['location']}: Sunny, 72°F"
                        })

                # Add tool results to conversation
                conversation.append({
                    "role": "user",
                    "content": tool_results
                })

                # Get final response
                final_response = await provider.generate_with_tools(
                    messages=conversation,
                    tools=tools,
                    system=system_prompt,
                    max_tokens=2048,
                    temperature=0.7
                )

                # Extract text from final response
                for block in final_response["content"]:
                    block_type = block.get("type") if isinstance(block, dict) else block.type
                    if block_type == "text":
                        text = block.get("text") if isinstance(block, dict) else block.text
                        print(text)

                # Add to conversation
                conversation.append({
                    "role": "assistant",
                    "content": final_response["content"]
                })
            else:
                # No tools, just text
                print(text_response)
                conversation.append({
                    "role": "assistant",
                    "content": response["content"]
                })

            print()

            # Show token usage
            print(f"[Tokens: {response['usage']['input_tokens']} in, {response['usage']['output_tokens']} out, Cost: $0.00]")
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            print()

    # Cleanup
    await provider.close()


if __name__ == "__main__":
    print("\nStarting BigFlavor Agent Local Chat...")
    print("Make sure Ollama is running (docker-compose up -d ollama)\n")

    try:
        asyncio.run(simple_chat_session())
    except KeyboardInterrupt:
        print("\n\nSession ended.")
