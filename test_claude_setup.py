"""
Quick test to verify Claude agent setup.
This tests the agent structure without making API calls.
"""

import sys
import os

def test_imports():
    """Test that all required packages are installed."""
    print("Testing imports...")
    
    try:
        import anthropic
        print("✅ anthropic package installed")
    except ImportError as e:
        print(f"❌ Failed to import anthropic: {e}")
        return False
    
    try:
        from claude_agent import ClaudeMusicAgent
        print("✅ claude_agent module imports successfully")
    except ImportError as e:
        print(f"❌ Failed to import claude_agent: {e}")
        return False
    
    return True


def test_agent_creation():
    """Test agent creation without API key."""
    print("\nTesting agent creation...")
    
    try:
        from claude_agent import ClaudeMusicAgent
        
        # Test without API key (should fail gracefully)
        os.environ.pop('ANTHROPIC_API_KEY', None)
        
        try:
            agent = ClaudeMusicAgent()
            print("❌ Agent should require API key but didn't")
            return False
        except ValueError as e:
            if "API key required" in str(e):
                print("✅ Agent correctly requires API key")
                return True
            else:
                print(f"❌ Unexpected error: {e}")
                return False
                
    except Exception as e:
        print(f"❌ Unexpected error during agent creation test: {e}")
        return False


def test_cost_estimation():
    """Test cost estimation logic."""
    print("\nTesting cost estimation...")
    
    try:
        from claude_agent import ClaudeMusicAgent
        
        # Create agent with dummy API key for testing
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test-key-for-testing-only'
        agent = ClaudeMusicAgent()
        
        # Simulate some token usage
        agent.total_input_tokens = 1000
        agent.total_output_tokens = 500
        
        costs = agent._estimate_cost()
        
        # Check cost calculation
        expected_input_cost = (1000 / 1_000_000) * 0.25  # $0.00025
        expected_output_cost = (500 / 1_000_000) * 1.25  # $0.000625
        expected_total = expected_input_cost + expected_output_cost  # $0.000875
        
        if abs(costs['input_cost_usd'] - expected_input_cost) < 0.0001:
            print(f"✅ Input cost calculation correct: ${costs['input_cost_usd']:.6f}")
        else:
            print(f"❌ Input cost incorrect. Expected ${expected_input_cost:.6f}, got ${costs['input_cost_usd']:.6f}")
            return False
        
        if abs(costs['total_cost_usd'] - expected_total) < 0.0001:
            print(f"✅ Total cost calculation correct: ${costs['total_cost_usd']:.6f}")
        else:
            print(f"❌ Total cost incorrect. Expected ${expected_total:.6f}, got ${costs['total_cost_usd']:.6f}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error during cost estimation test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_system_prompt():
    """Test system prompt generation."""
    print("\nTesting system prompt...")
    
    try:
        from claude_agent import ClaudeMusicAgent
        
        os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-test-key'
        agent = ClaudeMusicAgent()
        
        prompt = agent._get_default_system_prompt()
        
        if "Big Flavor Band" in prompt:
            print("✅ System prompt contains Big Flavor Band")
        else:
            print("❌ System prompt missing Big Flavor Band reference")
            return False
        
        if "RAG" in prompt or "semantic" in prompt.lower():
            print("✅ System prompt mentions RAG/semantic capabilities")
        else:
            print("⚠️  System prompt doesn't mention RAG capabilities")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during system prompt test: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 80)
    print("🧪 Claude Agent Setup Verification")
    print("=" * 80)
    print()
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Agent Creation", test_agent_creation()))
    results.append(("Cost Estimation", test_cost_estimation()))
    results.append(("System Prompt", test_system_prompt()))
    
    print("\n" + "=" * 80)
    print("Test Results Summary")
    print("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:.<40} {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("=" * 80)
    
    if all_passed:
        print("\n🎉 All tests passed! Your Claude agent is ready to use.")
        print("\nNext steps:")
        print("1. Get your API key from https://console.anthropic.com/")
        print("2. Set environment variable:")
        print("   $env:ANTHROPIC_API_KEY = 'sk-ant-your-key-here'")
        print("3. Run the agent:")
        print("   python claude_agent.py")
        return 0
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
