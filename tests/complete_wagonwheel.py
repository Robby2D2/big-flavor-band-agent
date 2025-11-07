"""
Test intelligent auto-clean on wagonwheel.mp3 - AI analyzes and optimizes automatically!
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


async def test_intelligent_auto_clean():
    """Test the new intelligent auto-clean feature."""
    
    print("=" * 70)
    print("INTELLIGENT AUTO-CLEAN TEST")
    print("AI-Driven Audio Analysis & Optimization")
    print("=" * 70)
    print()
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    input_file = str(project_root / "tests" / "wagonwheel.mp3")
    output_dir = project_root / "tests" / "wagonwheel_auto_clean"
    output_dir.mkdir(exist_ok=True)
    output_file = str(output_dir / "auto_clean_final.wav")
    
    print(f"Input:  {input_file}")
    print(f"Output: {output_file}\n")
    
    # Step 1: Analyze first to show what the AI detects
    print("=" * 70)
    print("STEP 1: AI Analysis - What does the audio need?")
    print("=" * 70)
    print()
    
    query1 = f"Analyze {input_file} and tell me what processing it needs"
    print(f"Query: {query1}\n")
    
    result1 = await agent.chat(query1)
    print("AI Analysis:")
    print(result1['response'])
    print()
    
    usage1 = result1['total_cost']
    print(f"[Tokens: {usage1['total_tokens']} | Cost: ${usage1['total_cost_usd']:.4f}]")
    
    print("\n" + "=" * 70)
    print("STEP 2: Intelligent Auto-Clean - Let AI do the work!")
    print("=" * 70)
    print()
    
    # Step 2: Auto-clean with moderate settings (keeps intermediate files)
    query2 = f"Automatically clean {input_file} and save to {output_file} with moderate aggressiveness, keep intermediate files so I can hear each step"
    print(f"Query: {query2}\n")
    
    result2 = await agent.chat(query2)
    print("Processing Result:")
    print(result2['response'])
    print()
    
    usage2 = result2['total_cost']
    print(f"[Tokens: {usage2['total_tokens']} | Cost: ${usage2['total_cost_usd']:.4f}]")
    
    # Summary
    print("\n" + "=" * 70)
    print("PROCESSING COMPLETE!")
    print("=" * 70)
    print()
    
    if Path(output_file).exists():
        size_mb = Path(output_file).stat().st_size / (1024 * 1024)
        print(f"✓ Final output: {Path(output_file).name} ({size_mb:.2f} MB)")
    else:
        print(f"⚠ Warning: Output file not found")
    
    # Show intermediate files if they exist
    steps_dir = output_dir / "auto_clean_final_steps"
    if steps_dir.exists():
        print(f"\n✓ Intermediate steps saved in: {steps_dir.name}/")
        for f in sorted(steps_dir.glob("*.wav")):
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name:<30} ({size_mb:.2f} MB)")
    
    total_tokens = usage1['total_tokens'] + usage2['total_tokens']
    total_cost = usage1['total_cost_usd'] + usage2['total_cost_usd']
    print(f"\nTotal Tokens: {total_tokens}")
    print(f"Total Cost: ${total_cost:.4f}")
    
    print("\n" + "=" * 70)
    print("🎵 Listen and Compare:")
    print("=" * 70)
    print("  Original:     tests/wagonwheel.mp3")
    print("  AI-Cleaned:   tests/wagonwheel_auto_clean/auto_clean_final.wav")
    print("\n  Check intermediate steps to hear the AI's processing:")
    print("  - 01_trimmed.wav       (AI detected where music starts/ends)")
    print("  - 02_denoised.wav      (AI measured noise and removed it)")
    print("  - 03_eq.wav            (AI balanced the frequencies)")
    print("  - 04_normalized.wav    (AI optimized dynamics)")
    print("  - 05_mastered.wav      (AI set optimal loudness)")
    print("\n  The AI analyzed your audio and chose the best settings")
    print("  automatically - no guessing required!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_intelligent_auto_clean())
