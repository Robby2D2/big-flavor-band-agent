"""
Test the intelligent auto-clean feature on wagonwheel.mp3
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src" / "agent"))
sys.path.insert(0, str(project_root / "src" / "production"))
sys.path.insert(0, str(project_root / "database"))

from big_flavor_agent import BigFlavorAgent


async def test_auto_clean():
    """Test the auto-clean feature."""
    
    print("=" * 70)
    print("Intelligent Auto-Clean Test on Wagonwheel.mp3")
    print("=" * 70)
    print()
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    input_file = str(project_root / "tests" / "wagonwheel.mp3")
    output_dir = project_root / "tests" / "wagonwheel_auto_clean"
    output_dir.mkdir(exist_ok=True)
    
    print(f"Input: {input_file}")
    print(f"Output directory: {output_dir}\n")
    
    # Test 1: Get analysis and recommendations
    print("=" * 70)
    print("TEST 1: Analyze and Get Recommendations")
    print("=" * 70)
    print()
    
    query1 = f"Analyze {input_file} and tell me what processing it needs"
    
    result1 = await agent.chat(query1)
    print(f"Query: {query1}\n")
    print(f"Response:\n{result1['response']}\n")
    print(f"[Tokens: {result1['total_cost']['total_tokens']} | Cost: ${result1['total_cost']['total_cost_usd']:.4f}]")
    
    print("\n\nPress Enter to continue to auto-clean test...")
    input()
    
    # Test 2: Auto-clean with moderate settings
    print("\n" + "=" * 70)
    print("TEST 2: Auto-Clean with Moderate Settings (keep intermediates)")
    print("=" * 70)
    print()
    
    output_file = str(output_dir / "auto_clean_moderate.wav")
    query2 = f"Automatically clean {input_file} and save to {output_file} with moderate aggressiveness, keep intermediate files"
    
    result2 = await agent.chat(query2)
    print(f"Query: {query2}\n")
    print(f"Response:\n{result2['response']}\n")
    print(f"[Tokens: {result2['total_cost']['total_tokens']} | Cost: ${result2['total_cost']['total_cost_usd']:.4f}]")
    
    # Check output
    if Path(output_file).exists():
        size_mb = Path(output_file).stat().st_size / (1024 * 1024)
        print(f"\n✓ Output created: {Path(output_file).name} ({size_mb:.2f} MB)")
    
    # Check for intermediate files
    steps_dir = output_dir / "auto_clean_moderate_steps"
    if steps_dir.exists():
        print(f"\n✓ Intermediate steps saved in: {steps_dir.name}/")
        for f in sorted(steps_dir.glob("*.wav")):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name:<30} ({size_mb:.2f} MB)")
    
    print("\n\nPress Enter to continue to aggressive test...")
    input()
    
    # Test 3: Auto-clean with aggressive settings
    print("\n" + "=" * 70)
    print("TEST 3: Auto-Clean with Aggressive Settings")
    print("=" * 70)
    print()
    
    output_file_aggressive = str(output_dir / "auto_clean_aggressive.wav")
    query3 = f"Clean {input_file} very aggressively and save to {output_file_aggressive}"
    
    result3 = await agent.chat(query3)
    print(f"Query: {query3}\n")
    print(f"Response:\n{result3['response']}\n")
    print(f"[Tokens: {result3['total_cost']['total_tokens']} | Cost: ${result3['total_cost']['total_cost_usd']:.4f}]")
    
    if Path(output_file_aggressive).exists():
        size_mb = Path(output_file_aggressive).stat().st_size / (1024 * 1024)
        print(f"\n✓ Output created: {Path(output_file_aggressive).name} ({size_mb:.2f} MB)")
    
    # Final summary
    print("\n" + "=" * 70)
    print("TESTING COMPLETE")
    print("=" * 70)
    print("\nOutput files to compare:")
    for f in sorted(output_dir.glob("*.wav")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name:<35} ({size_mb:.2f} MB)")
    
    total_cost = agent._estimate_cost()
    print(f"\nTotal Tokens: {total_cost['total_tokens']}")
    print(f"Total Cost: ${total_cost['total_cost_usd']:.4f}")
    
    print("\n" + "=" * 70)
    print("Listen and compare:")
    print("  1. Original: wagonwheel.mp3")
    print("  2. Auto-clean moderate: auto_clean_moderate.wav")
    print("  3. Auto-clean aggressive: auto_clean_aggressive.wav")
    print("\nThe AI-driven auto-clean should sound better than manual processing")
    print("because it analyzes the audio and chooses optimal settings!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_auto_clean())
