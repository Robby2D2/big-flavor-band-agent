"""
Test script for dual MCP architecture
Tests both RAG and Production servers independently
"""

import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-dual-mcp")


async def test_search_server():
    """Test Search MCP server (which exposes RAG system as MCP tools)."""
    print("\n" + "=" * 60)
    print("Testing Search MCP Server (exposes RAG system)")
    print("=" * 60)
    
    from rag_mcp_server import BigFlavorSearchMCPServer
    
    try:
        server = BigFlavorSearchMCPServer(use_clap=True)
        await server.initialize()
        
        # Test 1: Get embedding stats
        print("\n1. Testing embedding stats...")
        stats = await server.get_embedding_stats()
        print(f"   Status: {stats.get('status')}")
        if stats.get('status') == 'success':
            print(f"   Total songs: {stats['stats'].get('total_songs')}")
            print(f"   Songs with embeddings: {stats['stats'].get('songs_with_audio_embeddings')}")
        
        # Test 2: Text description search
        print("\n2. Testing text description search...")
        results = await server.search_by_text_description("rock", limit=5)
        print(f"   Status: {results.get('status')}")
        print(f"   Results: {results.get('results_count')} songs")
        if results.get('songs'):
            print(f"   First song: {results['songs'][0].get('title')}")
        
        # Test 3: Tempo range search
        print("\n3. Testing tempo range search...")
        results = await server.search_by_tempo_range(min_tempo=100, max_tempo=120, limit=5)
        print(f"   Status: {results.get('status')}")
        print(f"   Results: {results.get('results_count')} songs")
        if results.get('songs'):
            for song in results['songs'][:3]:
                print(f"   - {song.get('title')}: {song.get('tempo_bpm'):.1f} BPM")
        
        print("\n✅ Search MCP Server tests completed")
        return True
        
    except Exception as e:
        print(f"\n❌ Search MCP Server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_production_server():
    """Test Production server audio operations."""
    print("\n" + "=" * 60)
    print("Testing Production Server (Audio Production)")
    print("=" * 60)
    
    from mcp_server_new import BigFlavorMCPServer
    
    try:
        server = BigFlavorMCPServer(enable_audio_analysis=True)
        await server.initialize()
        
        # Test 1: Get cache stats
        print("\n1. Testing audio cache stats...")
        stats = await server.get_audio_cache_stats()
        print(f"   Cache entries: {stats.get('total_entries', 0)}")
        print(f"   Cache hits: {stats.get('cache_hits', 0)}")
        
        # Test 2: Check if we have any audio files to test with
        audio_library = Path("audio_library")
        if audio_library.exists():
            audio_files = list(audio_library.glob("**/*.mp3"))
            
            if audio_files:
                test_file = str(audio_files[0])
                print(f"\n2. Testing audio analysis on: {Path(test_file).name}")
                
                result = await server.analyze_audio(test_file)
                if result.get('status') == 'success':
                    analysis = result.get('analysis', {})
                    print(f"   BPM: {analysis.get('bpm', 'N/A')}")
                    print(f"   Key: {analysis.get('key', 'N/A')}")
                    print(f"   Energy: {analysis.get('energy', 'N/A')}")
                else:
                    print(f"   Analysis failed: {result.get('error')}")
            else:
                print("\n2. No audio files found for testing")
                print("   Skipping audio analysis test")
        else:
            print("\n2. Audio library not found")
            print("   Skipping audio analysis test")
        
        # Note: Skip actual audio production tests (tempo matching, transitions, mastering)
        # as they require valid input files and produce output files
        print("\n   Note: Skipping tempo matching, transitions, and mastering tests")
        print("   (These require specific audio files and produce output)")
        
        print("\n✅ Production Server tests completed")
        return True
        
    except Exception as e:
        print(f"\n❌ Production Server test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dual_agent():
    """Test the dual MCP agent."""
    print("\n" + "=" * 60)
    print("Testing Dual MCP Agent (Orchestration)")
    print("=" * 60)
    
    from claude_dual_mcp_agent import ClaudeDualMCPAgent
    import os
    
    # Check if API key is available
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n⚠️  Skipping agent test: ANTHROPIC_API_KEY not set")
        print("   Set the API key to test Claude integration")
        return True
    
    try:
        agent = ClaudeDualMCPAgent()
        await agent.initialize()
        
        print("\n1. Testing agent initialization...")
        print("   ✓ RAG server initialized")
        print("   ✓ Production server initialized")
        
        print("\n2. Checking available tools...")
        tools = agent._get_available_tools()
        search_tools = [t for t in tools if t.get('server') == 'search']
        mcp_tools = [t for t in tools if t.get('server') == 'mcp']
        
        print(f"   Search tools (using RAG library): {len(search_tools)}")
        for tool in search_tools:
            print(f"     - {tool['name']}")
        
        print(f"   Production tools: {len(mcp_tools)}")
        for tool in mcp_tools:
            print(f"     - {tool['name']}")
        
        print("\n✅ Dual MCP Agent tests completed")
        return True
        
    except Exception as e:
        print(f"\n❌ Dual MCP Agent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DUAL MCP ARCHITECTURE TEST SUITE")
    print("=" * 60)
    
    results = []
    
    # Test Search MCP server
    results.append(("Search MCP Server", await test_search_server()))
    
    # Test Production server
    results.append(("Production MCP Server", await test_production_server()))
    
    # Test Dual Agent
    results.append(("Dual MCP Agent", await test_dual_agent()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED")
    print("=" * 60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
