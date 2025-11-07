"""
Test script to verify Big Flavor Band AI Agent installation and functionality.
"""

import sys
import asyncio


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        import agent
        print("  ✓ agent module")
    except ImportError as e:
        print(f"  ✗ agent module: {e}")
        return False
    
    try:
        import recommendation_engine
        print("  ✓ recommendation_engine module")
    except ImportError as e:
        print(f"  ✗ recommendation_engine module: {e}")
        return False
    
    try:
        import album_curator
        print("  ✓ album_curator module")
    except ImportError as e:
        print(f"  ✗ album_curator module: {e}")
        return False
    
    try:
        import audio_analyzer
        print("  ✓ audio_analyzer module")
    except ImportError as e:
        print(f"  ✗ audio_analyzer module: {e}")
        return False
    
    # MCP server requires mcp package
    try:
        import mcp_server
        print("  ✓ mcp_server module")
    except ImportError as e:
        print(f"  ⚠ mcp_server module (requires 'mcp' package): {e}")
        print("    Install with: pip install mcp")
    
    return True


async def test_agent_basic():
    """Test basic agent functionality."""
    print("\nTesting agent initialization...")
    
    try:
        from agent import BigFlavorAgent
        
        agent = BigFlavorAgent()
        await agent.initialize()
        print("  ✓ Agent initialized successfully")
        
        # Test song library loaded
        if len(agent.song_library) > 0:
            print(f"  ✓ Song library loaded ({len(agent.song_library)} songs)")
        else:
            print("  ✗ Song library is empty")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Agent initialization failed: {e}")
        return False


async def test_recommendation_engine():
    """Test recommendation engine."""
    print("\nTesting recommendation engine...")
    
    try:
        from agent import BigFlavorAgent
        
        agent = BigFlavorAgent()
        await agent.initialize()
        
        # Test next song suggestion
        result = await agent.suggest_next_song(current_song_id="song_001")
        if result and "recommended_song" in result:
            print(f"  ✓ Next song recommendation works")
            print(f"    Suggested: {result['recommended_song']['title']}")
        else:
            print("  ✗ Next song recommendation failed")
            return False
        
        # Test similar songs
        result = await agent.suggest_similar_songs("song_002", limit=3)
        if result and "similar_songs" in result:
            print(f"  ✓ Similar songs search works")
            print(f"    Found {len(result['similar_songs'])} similar songs")
        else:
            print("  ✗ Similar songs search failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Recommendation engine test failed: {e}")
        return False


async def test_album_curator():
    """Test album curation."""
    print("\nTesting album curator...")
    
    try:
        from agent import BigFlavorAgent
        
        agent = BigFlavorAgent()
        await agent.initialize()
        
        # Test album creation
        result = await agent.create_album_suggestion(theme="rock", target_duration_minutes=30)
        if result and "tracks" in result:
            print(f"  ✓ Album creation works")
            print(f"    Created album with {len(result['tracks'])} tracks")
        else:
            print("  ✗ Album creation failed")
            return False
        
        # Test flow analysis
        result = await agent.analyze_album_flow(["song_001", "song_002"])
        if result and "overall_flow_score" in result:
            print(f"  ✓ Flow analysis works")
            print(f"    Flow score: {result['overall_flow_score']}/100")
        else:
            print("  ✗ Flow analysis failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Album curator test failed: {e}")
        return False


async def test_audio_analyzer():
    """Test audio analyzer."""
    print("\nTesting audio analyzer...")
    
    try:
        from agent import BigFlavorAgent
        
        agent = BigFlavorAgent()
        await agent.initialize()
        
        # Test audio suggestions
        result = await agent.get_audio_engineering_suggestions("song_001")
        if result and "improvement_suggestions" in result:
            print(f"  ✓ Audio engineering suggestions work")
            print(f"    Quality: {result['current_quality']}")
        else:
            print("  ✗ Audio engineering suggestions failed")
            return False
        
        # Test quality comparison
        result = await agent.compare_song_quality(["song_001", "song_002", "song_003"])
        if result and "quality_ranking" in result:
            print(f"  ✓ Quality comparison works")
            print(f"    Average score: {result['average_quality_score']}/100")
        else:
            print("  ✗ Quality comparison failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Audio analyzer test failed: {e}")
        return False


async def run_all_tests():
    """Run all tests."""
    print("="*60)
    print("Big Flavor Band AI Agent - Test Suite")
    print("="*60)
    
    results = []
    
    # Test imports
    results.append(("Imports", test_imports()))
    
    # Test async components
    results.append(("Agent Basic", await test_agent_basic()))
    results.append(("Recommendation Engine", await test_recommendation_engine()))
    results.append(("Album Curator", await test_album_curator()))
    results.append(("Audio Analyzer", await test_audio_analyzer()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! Your installation is working correctly.")
        print("\nYou're ready to rock! 🎸")
        return 0
    else:
        print("\n⚠ Some tests failed. Check the errors above.")
        print("\nCommon issues:")
        print("  • Missing dependencies: pip install -r requirements.txt")
        print("  • MCP package not installed: pip install mcp")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
