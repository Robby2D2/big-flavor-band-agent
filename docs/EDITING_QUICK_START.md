# Audio Editing Features - Quick Start

The Big Flavor Band Agent now includes professional audio editing capabilities for processing raw live recordings into production-ready tracks.

## What's New

Six new editing tools for processing raw recordings:

1. **trim_silence** - Remove dead space from beginning/end
2. **reduce_noise** - Remove background noise, hum, feedback
3. **correct_pitch** - Fix wrong notes or apply auto-tune
4. **normalize_audio** - Even out levels with compression
5. **apply_eq** - Shape sound with EQ filters
6. **remove_artifacts** - Remove clicks, pops, glitches

## Quick Examples

### Process a Raw Recording

```python
from big_flavor_agent import BigFlavorAgent

agent = BigFlavorAgent()
await agent.initialize()

# Complete workflow
await agent.chat("""
Take my raw recording raw_session.wav and turn it into a 
production-ready track. Save as final_master.wav
""")
```

### Individual Tools

```python
# Remove background noise
await agent.chat("Remove noise from guitar.wav")

# Clean up and normalize
await agent.chat("Clean up drums.wav and normalize the levels")

# Full polish
await agent.chat("Polish recording.wav: trim silence, reduce noise, EQ, and master")
```

## Recommended Workflow

The agent follows this professional workflow for raw recordings:

1. **Trim Silence** - Clean beginning/end
2. **Reduce Noise** - Remove background noise
3. **Correct Pitch** - Fix tuning issues (optional)
4. **Apply EQ** - Remove mud, add clarity
5. **Normalize** - Even out levels
6. **Master** - Final loudness and polish

## Testing

Run the test suite to see the editing tools in action:

```bash
python tests/test_editing_tools.py
```

This will demonstrate:
- Available editing tools
- Recommended workflows
- Example conversations

## Files Modified

### Core Files
- `src/production/big_flavor_mcp.py` - Added 6 new editing methods
- `src/agent/big_flavor_agent.py` - Added tool definitions and routing
- `setup/requirements.txt` - Added scipy dependency

### Documentation
- `docs/EDITING_CAPABILITIES.md` - Complete editing guide
- `tests/test_editing_tools.py` - Test script

## Technical Details

**Libraries Used:**
- librosa - Audio effects and analysis
- scipy - Signal processing and filters
- numpy - Numerical operations
- soundfile - Audio I/O

**Key Algorithms:**
- Spectral gating for noise reduction
- Phase vocoder for pitch correction
- Butterworth filters for EQ
- Derivative-based artifact detection

## Next Steps

1. Read `docs/EDITING_CAPABILITIES.md` for detailed documentation
2. Run `tests/test_editing_tools.py` to see examples
3. Try processing your own recordings!

## Usage Notes

- All tools preserve original files - they create new output files
- Default parameters work well for most cases
- Follow the recommended workflow for best results
- Start with good source recordings
- Listen critically and adjust as needed

## Example Conversation

```
User: I have a raw recording with background noise. Can you clean it up?

Agent: I'll process your recording through a professional workflow:

1. First, I'll trim any silence from the beginning and end
2. Then reduce the background noise using spectral gating
3. Apply EQ to remove low-frequency rumble
4. Normalize the levels for consistent volume
5. Apply final mastering for professional loudness

Let me start processing...
[Tool executions...]

Done! Your cleaned recording is ready. The noise reduction 
achieved a 15dB reduction in background noise, and the final 
master meets streaming platform standards at -14 LUFS.
```

## Support

For more information:
- Full documentation: `docs/EDITING_CAPABILITIES.md`
- Agent setup: `docs/CLAUDE_AGENT_SETUP.md`
- Architecture: `docs/DUAL_MCP_ARCHITECTURE.md`
