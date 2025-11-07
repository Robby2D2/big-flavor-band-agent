"""
Test the professional editing workflow on wagonwheel.mp3
This will process the file through all editing steps.
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


async def process_wagonwheel():
    """Process wagonwheel.mp3 through the complete editing workflow."""
    
    print("=" * 70)
    print("Big Flavor Band - Professional Editing Workflow Test")
    print("Processing: wagonwheel.mp3")
    print("=" * 70)
    print()
    
    # Initialize agent
    print("Initializing agent...")
    agent = BigFlavorAgent()
    await agent.initialize()
    print("✓ Agent initialized\n")
    
    # Define file paths
    input_file = str(project_root / "tests" / "wagonwheel.mp3")
    output_dir = project_root / "tests" / "wagonwheel_processed"
    output_dir.mkdir(exist_ok=True)
    
    # Check if input file exists
    if not Path(input_file).exists():
        print(f"❌ Error: Input file not found: {input_file}")
        print("\nPlease ensure wagonwheel.mp3 is in the tests/ directory.")
        return
    
    print(f"Input file: {input_file}")
    print(f"Output directory: {output_dir}\n")
    
    # Define processing steps
    steps = [
        {
            "name": "Step 1: Trim Silence",
            "query": f"Trim silence from {input_file}, save to {output_dir / '01_trimmed.wav'}",
            "output": output_dir / "01_trimmed.wav"
        },
        {
            "name": "Step 2: Reduce Noise",
            "query": f"Reduce noise from {output_dir / '01_trimmed.wav'}, save to {output_dir / '02_denoised.wav'}",
            "output": output_dir / "02_denoised.wav"
        },
        {
            "name": "Step 3: Apply EQ (High-pass at 80Hz)",
            "query": f"Apply high-pass filter at 80Hz to {output_dir / '02_denoised.wav'}, save to {output_dir / '03_eq.wav'}",
            "output": output_dir / "03_eq.wav"
        },
        {
            "name": "Step 4: Normalize Audio",
            "query": f"Normalize {output_dir / '03_eq.wav'} with compression, save to {output_dir / '04_normalized.wav'}",
            "output": output_dir / "04_normalized.wav"
        },
        {
            "name": "Step 5: Apply Mastering",
            "query": f"Apply mastering to {output_dir / '04_normalized.wav'}, save to {output_dir / '05_final_master.wav'}",
            "output": output_dir / "05_final_master.wav"
        }
    ]
    
    print("=" * 70)
    print("PROCESSING WORKFLOW")
    print("=" * 70)
    print()
    
    # Process each step
    total_tokens = 0
    total_cost = 0.0
    
    for i, step in enumerate(steps, 1):
        print(f"\n{'=' * 70}")
        print(f"{step['name']}")
        print(f"{'=' * 70}")
        print(f"Query: {step['query']}\n")
        
        try:
            result = await agent.chat(step['query'])
            
            print(f"Response:\n{result['response']}\n")
            
            # Check if file was created
            if step['output'].exists():
                size_mb = step['output'].stat().st_size / (1024 * 1024)
                print(f"✓ Output created: {step['output'].name} ({size_mb:.2f} MB)")
            else:
                print(f"⚠ Warning: Expected output file not found: {step['output'].name}")
            
            # Track usage
            usage = result['total_cost']
            total_tokens += usage['total_tokens']
            total_cost += usage['total_cost_usd']
            
            print(f"[Tokens: {usage['total_tokens']} | Cost: ${usage['total_cost_usd']:.4f}]")
            
        except Exception as e:
            print(f"❌ Error in {step['name']}: {e}")
            print("\nContinuing with next step...")
    
    # Final summary
    print("\n" + "=" * 70)
    print("PROCESSING COMPLETE!")
    print("=" * 70)
    print()
    print("Output Files:")
    print(f"  Original:      {input_file}")
    for step in steps:
        if step['output'].exists():
            size_mb = step['output'].stat().st_size / (1024 * 1024)
            print(f"  {step['output'].name:<20} ({size_mb:.2f} MB)")
    
    print()
    print("=" * 70)
    print("COMPARISON GUIDE")
    print("=" * 70)
    print()
    print("Listen to these files in order to hear the improvements:")
    print()
    print("1. Original:         tests/wagonwheel.mp3")
    print(f"2. After Trimming:   {output_dir.name}/01_trimmed.wav")
    print(f"3. After Denoising:  {output_dir.name}/02_denoised.wav")
    print(f"4. After EQ:         {output_dir.name}/03_eq.wav")
    print(f"5. After Normalize:  {output_dir.name}/04_normalized.wav")
    print(f"6. Final Master:     {output_dir.name}/05_final_master.wav")
    print()
    print("Key improvements to listen for:")
    print("  • Cleaner start/end (no silence)")
    print("  • Reduced background noise and hiss")
    print("  • Clearer, less muddy sound (EQ)")
    print("  • More consistent volume (normalization)")
    print("  • Professional loudness (mastering)")
    print()
    print("=" * 70)
    print(f"Total Tokens Used: {total_tokens}")
    print(f"Total Cost: ${total_cost:.4f}")
    print("=" * 70)


async def quick_process():
    """Quick single-command processing."""
    
    print("\n" + "=" * 70)
    print("QUICK PROCESS: Single Command Workflow")
    print("=" * 70)
    print()
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    input_file = str(project_root / "tests" / "wagonwheel.mp3")
    output_file = str(project_root / "tests" / "wagonwheel_processed" / "quick_master.wav")
    
    query = f"""
    Process {input_file} through the complete professional workflow:
    1. Trim silence
    2. Reduce noise  
    3. Apply EQ (high-pass at 80Hz)
    4. Normalize with compression
    5. Apply mastering
    
    Save the final output to {output_file}
    
    Provide a summary of what was done at each step.
    """
    
    print("Processing with single command...\n")
    
    result = await agent.chat(query)
    
    print("=" * 70)
    print("AGENT RESPONSE")
    print("=" * 70)
    print(result['response'])
    print()
    print("=" * 70)
    
    usage = result['total_cost']
    print(f"Tokens: {usage['total_tokens']} | Cost: ${usage['total_cost_usd']:.4f}")


async def main():
    """Main entry point."""
    
    print("\nBig Flavor Band - Wagonwheel Editing Test")
    print("=" * 70)
    print("\nThis will process wagonwheel.mp3 through the complete workflow.")
    print("\nOptions:")
    print("1. Step-by-step processing (creates all intermediate files)")
    print("2. Quick process (agent decides workflow)")
    print()
    
    choice = input("Select option (1-2, or Enter for step-by-step): ").strip()
    
    if not choice or choice == "1":
        await process_wagonwheel()
    elif choice == "2":
        await quick_process()
    else:
        print("Invalid choice. Exiting.")
        return
    
    print("\n✓ Done! Check the output files in tests/wagonwheel_processed/")


if __name__ == "__main__":
    asyncio.run(main())
