"""
Simplified BigFlavor Agent - Works with Ollama, no database needed
Demonstrates tool calling with music-related tools (simulated)
"""
import asyncio
import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src" / "llm"))

from llm_provider import get_llm_provider


async def chat_with_ollama():
    """Chat session with Ollama using simulated music tools"""

    print("=" * 70)
    print("BigFlavor Music Agent (Ollama - Simulated Mode)")
    print("=" * 70)
    print()
    print("NOTE: This is a demo mode without database access.")
    print("Music searches are simulated to show tool calling in action.")
    print()
    print("Try asking:")
    print("  - What songs sound like Led Zeppelin?")
    print("  - Find me some upbeat rock songs")
    print("  - What's the tempo of a typical blues song?")
    print()
    print("Commands: 'quit' to exit")
    print("=" * 70)
    print()

    # Create Ollama provider
    print("Connecting to Ollama...")
    provider = get_llm_provider(
        provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1:8b"
    )
    print(f"Connected: {provider.model}")
    print()

    # Define music-related tools (simulated - no database)
    tools = [
        {
            "name": "search_songs_by_description",
            "description": "Search for songs matching a text description like genre, mood, or artist style. Returns a list of matching songs.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the desired music (e.g., 'upbeat rock', 'like Led Zeppelin', 'blues', 'jazzy')"
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results to return (default: 10)"
                    }
                },
                "required": ["description"]
            }
        },
        {
            "name": "find_song_by_title",
            "description": "Find a specific song by its title. Returns song details including tempo, key, and duration.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The song title to search for"
                    }
                },
                "required": ["title"]
            }
        },
        {
            "name": "search_by_tempo",
            "description": "Find songs within a specific tempo range (BPM - beats per minute). Great for finding songs at a specific speed.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "min_tempo": {
                        "type": "number",
                        "description": "Minimum tempo in BPM (e.g., 120)"
                    },
                    "max_tempo": {
                        "type": "number",
                        "description": "Maximum tempo in BPM (e.g., 140)"
                    }
                },
                "required": []
            }
        }
    ]

    system_prompt = """You are a helpful music assistant for the Big Flavor Band catalog.
You have access to tools to search for songs by description, title, and tempo.

When users ask about music, use the appropriate tools:
- For style/genre questions: use search_songs_by_description
- For specific songs: use find_song_by_title
- For tempo/speed: use search_by_tempo

Be friendly and enthusiastic about music!"""

    conversation = []

    # Simulated song database
    simulated_songs = {
        "led zeppelin": [
            {"title": "Mountain Road", "artist": "Big Flavor", "tempo": 98, "key": "Am", "style": "blues rock"},
            {"title": "Electric Highway", "artist": "Big Flavor", "tempo": 110, "key": "E", "style": "hard rock"},
            {"title": "Stairway Home", "artist": "Big Flavor", "tempo": 72, "key": "Am", "style": "folk rock"}
        ],
        "upbeat rock": [
            {"title": "Sunrise Jam", "artist": "Big Flavor", "tempo": 145, "key": "G", "style": "rock"},
            {"title": "Highway 61", "artist": "Big Flavor", "tempo": 138, "key": "A", "style": "rock"},
            {"title": "Electric Slide", "artist": "Big Flavor", "tempo": 142, "key": "D", "style": "rock"}
        ],
        "blues": [
            {"title": "Mississippi Blues", "artist": "Big Flavor", "tempo": 85, "key": "E", "style": "blues"},
            {"title": "Delta Morning", "artist": "Big Flavor", "tempo": 92, "key": "A", "style": "blues"}
        ]
    }

    # Chat loop
    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye!")
                break

            conversation.append({
                "role": "user",
                "content": user_input
            })

            print("\nAssistant: ", end="", flush=True)

            # Get response
            response = await provider.generate_with_tools(
                messages=conversation,
                tools=tools,
                system=system_prompt,
                max_tokens=2048,
                temperature=0.7
            )

            # Process tool calls
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

            # Handle tool calls
            if tool_calls:
                print(f"[Using tools: {', '.join(t[0] for t in tool_calls)}]")

                conversation.append({
                    "role": "assistant",
                    "content": response["content"]
                })

                # Simulate tool results
                tool_results = []
                for i, (tool_name, tool_input) in enumerate(tool_calls):
                    if tool_name == "search_songs_by_description":
                        desc = tool_input["description"].lower()
                        # Find matching songs
                        results = []
                        for key in simulated_songs:
                            if key in desc:
                                results = simulated_songs[key]
                                break
                        if not results:
                            results = simulated_songs.get("upbeat rock", [])[:3]

                        result_text = f"Found {len(results)} songs:\n"
                        for song in results:
                            result_text += f"- {song['title']} ({song['tempo']} BPM, {song['key']}, {song['style']})\n"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": f"tool_{i}",
                            "content": result_text
                        })

                    elif tool_name == "find_song_by_title":
                        title = tool_input["title"]
                        result_text = f"Song: {title}\nTempo: 110 BPM\nKey: A major\nDuration: 4:32\nStyle: Rock"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": f"tool_{i}",
                            "content": result_text
                        })

                    elif tool_name == "search_by_tempo":
                        min_t = tool_input.get("min_tempo", 0)
                        max_t = tool_input.get("max_tempo", 200)
                        result_text = f"Found 5 songs with tempo {min_t}-{max_t} BPM:\n"
                        result_text += "- Fast Lane (130 BPM)\n- Quick Step (135 BPM)\n- Speed Racer (142 BPM)"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": f"tool_{i}",
                            "content": result_text
                        })

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

                for block in final_response["content"]:
                    block_type = block.get("type") if isinstance(block, dict) else block.type
                    if block_type == "text":
                        text = block.get("text") if isinstance(block, dict) else block.text
                        print(text)

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
            print(f"[{response['usage']['input_tokens']} in, {response['usage']['output_tokens']} out, $0.00]")
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
            print()

    await provider.close()


if __name__ == "__main__":
    asyncio.run(chat_with_ollama())
