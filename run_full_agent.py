"""
Run the FULL BigFlavorAgent with:
- Real PostgreSQL database (1,341 songs!)
- Ollama LLM (free, local)
- Complete RAG search tools
- Audio analysis tools
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src" / "agent"))
sys.path.insert(0, str(project_root / "src" / "llm"))

# Set environment to use Ollama
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "llama3.1:8b"

# Database connection (disable SSL for local development)
os.environ["DATABASE_URL"] = "postgresql://bigflavor:bigflavor_dev_pass@localhost:5432/bigflavor?sslmode=disable"


async def run_full_agent():
    """Run the full BigFlavorAgent with database and all tools"""

    print("=" * 80)
    print("BigFlavor Band AI Agent - FULL VERSION")
    print("=" * 80)
    print()
    print("System Info:")
    print(f"  LLM: Ollama (llama3.1:8b)")
    print(f"  Database: PostgreSQL @ localhost:5432")
    print(f"  Cost: $0.00 (Ollama is free!)")
    print()
    print("Initializing...")
    print()

    try:
        from big_flavor_agent import BigFlavorAgent

        # Create agent with Ollama
        print("[1/3] Creating BigFlavorAgent with Ollama...")
        agent = BigFlavorAgent(
            llm_provider="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.1:8b"
        )
        print("  [OK] Agent created")
        print()

        # Initialize (connects to database, loads RAG system)
        print("[2/3] Initializing database and RAG system...")
        print("  This may take a moment...")
        await agent.initialize()
        print("  [OK] Database connected")
        print("  [OK] RAG system ready")
        print()

        # Check database stats
        print("[3/3] Loading music catalog...")
        # Get song count
        song_count = await agent.db_manager.execute(
            "SELECT COUNT(*) as count FROM songs"
        )
        count = song_count[0]['count'] if song_count else 0
        print(f"  [OK] {count:,} songs available!")
        print()

        print("=" * 80)
        print("Ready to chat!")
        print("=" * 80)
        print()
        print("Available Tools:")
        print("  🔍 Search by text description (genres, moods, themes)")
        print("  🎵 Search by audio similarity (sound-alike)")
        print("  📝 Search lyrics by keyword")
        print("  🎼 Find songs by title")
        print("  🎹 Search by tempo/BPM range")
        print("  🎛️ Hybrid search (combine multiple criteria)")
        if agent.production_server:
            print("  🎚️ Audio analysis & processing tools")
        print()
        print("Example queries:")
        print("  - What BigFlavor songs sound like Led Zeppelin?")
        print("  - Find me upbeat rock songs around 140 BPM")
        print("  - Songs with the word 'love' in the lyrics")
        print("  - What's the tempo of 'Going to California'?")
        print()
        print("Commands: 'quit' to exit, 'reset' to clear history")
        print("=" * 80)
        print()

        # Chat loop
        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\nGoodbye!")
                    break

                if user_input.lower() == 'reset':
                    agent.reset_conversation()
                    print("Conversation history cleared.\n")
                    continue

                # Get response from agent
                print("\nAssistant: ", end="", flush=True)

                result = await agent.chat(user_input)

                # Print response
                response_text = result.get("response", "")
                print(response_text)
                print()

                # Show usage stats
                usage = result.get("usage", {})
                cost = result.get("total_cost", {})

                stats = f"[Tokens: {usage.get('input_tokens', 0)} in, {usage.get('output_tokens', 0)} out"
                if cost.get('total_cost_usd', 0) == 0:
                    stats += ", Cost: $0.00 - FREE!]"
                else:
                    stats += f", Cost: ${cost.get('total_cost_usd', 0):.4f}]"

                print(stats)
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
        print("\nCleaning up...")
        await agent.db_manager.close()
        if hasattr(agent.llm_provider, 'close'):
            await agent.llm_provider.close()
        print("Done!")

    except ImportError as e:
        print("=" * 80)
        print("ERROR: Missing Dependencies")
        print("=" * 80)
        print()
        print(f"Import error: {e}")
        print()
        print("Make sure you've installed all dependencies:")
        print("  pip install -r setup/requirements.txt")
        print()
        print("And activated your virtual environment:")
        print("  .\\venv\\Scripts\\Activate.ps1")
        print()
        return 1

    except Exception as e:
        print("=" * 80)
        print("ERROR: Startup Failed")
        print("=" * 80)
        print()
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        print("Common issues:")
        print("  1. Database not running: docker-compose up -d postgres")
        print("  2. Ollama not running: docker-compose up -d ollama")
        print("  3. Wrong database password in DATABASE_URL")
        print()
        return 1

    return 0


if __name__ == "__main__":
    print()
    print("Starting BigFlavor Agent with Ollama + Real Database...")
    print()

    try:
        exit_code = asyncio.run(run_full_agent())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
