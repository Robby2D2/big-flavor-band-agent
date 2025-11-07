# Audio Editing Capabilities

The Big Flavor Band Agent now includes comprehensive audio editing tools for processing raw live recordings into production-ready tracks.

## Overview

These editing tools are designed specifically for the workflow of recording live band performances and turning them into polished, professional-quality audio files.

## Available Editing Tools

### 1. **trim_silence**
Remove silence from the beginning and end of audio recordings.

**Use Case:** Clean up the dead space before the band starts playing and after they finish.

**Parameters:**
- `file_path`: Path to the audio file to trim
- `threshold_db`: Silence threshold in dB (default: -40)
- `output_path`: Output path for trimmed file

**Example:**
```python
await agent.chat("Trim the silence from raw_recording.wav")
```

---

### 2. **reduce_noise**
Remove background noise, hum, hiss, and feedback from audio recordings.

**Use Case:** Clean up room noise, AC hum, electrical buzz, and other unwanted background sounds common in live recordings.

**How It Works:**
- Samples the beginning of the audio to create a noise profile
- Uses spectral gating to reduce frequencies matching the noise
- Applies high-pass filter to remove low-frequency rumble

**Parameters:**
- `file_path`: Path to the audio file to clean
- `noise_profile_duration`: Duration in seconds to sample for noise profile (default: 1.0)
- `reduction_strength`: Noise reduction strength 0-1 (default: 0.7)
- `output_path`: Output path for cleaned file

**Example:**
```python
await agent.chat("Remove noise from recording.wav, save as clean.wav")
```

---

### 3. **correct_pitch**
Apply pitch correction to fix wrong notes or tuning issues.

**Use Case:** Fix out-of-tune notes, correct pitch drift, or apply auto-tune effect.

**Features:**
- Manual pitch shift by semitones
- Automatic pitch correction to nearest notes (auto-tune)
- Preserves timing while adjusting pitch

**Parameters:**
- `file_path`: Path to the audio file to correct
- `semitones`: Semitones to shift (default: 0 for auto-tune)
- `auto_tune`: Enable automatic pitch correction (default: false)
- `output_path`: Output path for corrected file

**Examples:**
```python
# Manual pitch shift
await agent.chat("Shift guitar.wav up 2 semitones")

# Auto-tune
await agent.chat("Auto-tune vocals.wav to nearest notes")
```

---

### 4. **normalize_audio**
Normalize audio levels and apply compression for consistent volume.

**Use Case:** Even out the dynamics, ensure consistent loudness throughout the track.

**Features:**
- Peak normalization to target dB level
- Optional dynamic range compression
- Prevents clipping

**Parameters:**
- `file_path`: Path to the audio file to normalize
- `target_level_db`: Target peak level in dB (default: -3)
- `apply_compression`: Apply compression for dynamic range control (default: true)
- `output_path`: Output path for normalized file

**Example:**
```python
await agent.chat("Normalize levels on drums.wav with compression")
```

---

### 5. **apply_eq**
Apply equalizer filters to shape the sound.

**Use Case:** Remove muddy low frequencies, reduce harsh highs, boost presence frequencies, clean up the mix.

**Features:**
- High-pass filter (removes low-end rumble)
- Low-pass filter (removes high-frequency noise)
- Parametric boost at specific frequency

**Parameters:**
- `file_path`: Path to the audio file to EQ
- `high_pass_freq`: High-pass filter frequency in Hz (default: 30)
- `low_pass_freq`: Low-pass filter frequency in Hz (optional)
- `boost_freq`: Frequency in Hz to boost (optional)
- `boost_db`: Boost amount in dB (default: 3)
- `output_path`: Output path for EQ'd file

**Example:**
```python
await agent.chat("Apply high-pass filter at 80Hz to bass.wav, remove mud")
```

---

### 6. **remove_artifacts**
Detect and remove clicks, pops, and digital glitches from audio.

**Use Case:** Clean up recording artifacts, cable pops, mic bumps, digital errors.

**How It Works:**
- Detects rapid amplitude changes (clicks/pops)
- Interpolates smooth audio over artifact regions
- Applies gentle smoothing

**Parameters:**
- `file_path`: Path to the audio file to clean
- `sensitivity`: Detection sensitivity 0-1 (default: 0.5)
- `output_path`: Output path for cleaned file

**Example:**
```python
await agent.chat("Remove clicks and pops from recording.wav")
```

---

## Recommended Workflow for Raw Recordings

When processing a raw live recording, the agent will suggest this professional workflow:

### Step 1: Trim Silence
```python
trim_silence("raw_recording.wav", threshold_db=-40, output="01_trimmed.wav")
```
Removes dead space at beginning and end.

### Step 2: Reduce Noise
```python
reduce_noise("01_trimmed.wav", reduction_strength=0.7, output="02_denoised.wav")
```
Removes background noise, hum, and hiss.

### Step 3: Correct Pitch (if needed)
```python
correct_pitch("02_denoised.wav", auto_tune=True, output="03_tuned.wav")
```
Fixes any tuning issues or wrong notes.

### Step 4: Apply EQ
```python
apply_eq("03_tuned.wav", high_pass_freq=80, output="04_eq.wav")
```
Removes mud, adds clarity and presence.

### Step 5: Normalize
```python
normalize_audio("04_eq.wav", apply_compression=True, output="05_normalized.wav")
```
Evens out levels with gentle compression.

### Step 6: Master
```python
apply_mastering("05_normalized.wav", target_loudness=-14.0, output="final_master.wav")
```
Final loudness and polish for distribution.

---

## Usage Examples

### Complete Production Workflow
```python
await agent.chat("""
Take my raw recording raw_band_session.wav and turn it into a production-ready track.
Save the final output as final_master.wav
""")
```

The agent will execute all steps and provide feedback at each stage.

### Individual Tool Usage

**Just remove noise:**
```python
await agent.chat("Remove noise from guitar_take_3.wav")
```

**Clean up and normalize:**
```python
await agent.chat("Clean up the noise and normalize levels on drums.wav")
```

**Full polish:**
```python
await agent.chat("Polish this raw recording: remove silence, reduce noise, EQ, and master")
```

---

## Technical Details

### Audio Processing Libraries
- **librosa**: Audio analysis and effects
- **scipy**: Signal processing and filters
- **numpy**: Numerical operations
- **soundfile**: Audio I/O

### Algorithms Used

**Noise Reduction:**
- Spectral gating using STFT
- Noise profile estimation
- Soft masking with configurable strength

**Pitch Correction:**
- Pitch tracking using librosa piptrack
- Semitone quantization for auto-tune
- Phase vocoder for time-stretching

**EQ Filtering:**
- Butterworth filters (4th order)
- Peaking EQ for frequency boost
- High-pass and low-pass filters

**Artifact Removal:**
- Derivative-based detection
- Linear interpolation repair
- Savitzky-Golay smoothing

---

## Performance Tips

1. **Start with good recordings**: These tools are powerful but can't fix everything. Start with the best possible source material.

2. **Use conservative settings**: Start with default parameters and adjust if needed. Over-processing can degrade quality.

3. **Process in order**: Follow the recommended workflow for best results. Each step prepares the audio for the next.

4. **Keep originals**: Always work on copies. Save intermediate steps so you can go back if needed.

5. **Listen critically**: Use the agent's automatic workflow, but listen to results and ask for adjustments.

---

## Example Conversations

**User:** "I have a raw recording of our jam session. Can you clean it up and make it sound professional?"

**Agent:** "I'll process your raw recording through a professional editing workflow:
1. First, I'll trim the silence from the beginning and end
2. Remove background noise and hum
3. Apply EQ to remove mud and add clarity
4. Normalize the levels with compression
5. Apply final mastering for loudness

Let me start..."

---

**User:** "The guitar track has some background noise. Can you fix it?"

**Agent:** "I'll use the noise reduction tool to remove the background noise from your guitar track. This will sample the noise profile and filter it out while preserving the guitar sound..."

---

**User:** "Make this sound like a record"

**Agent:** "I'll process your audio through the full production chain to make it sound polished and radio-ready:
- Trim silence
- Reduce noise
- Apply EQ (remove rumble below 80Hz, add presence)
- Compress dynamics
- Master to -14 LUFS
This will give it that professional, finished sound..."

---

## Future Enhancements

Potential future additions:
- Multi-band compression
- Stereo widening
- Reverb and spatial effects
- Spectral repair for severe artifacts
- Vocal isolation
- Stem separation

---

## Support

For questions or issues with the editing tools, check:
- `docs/QUICK_START_REAL_SONGS.md` for basic usage
- `docs/CLAUDE_AGENT_SETUP.md` for agent configuration
- GitHub issues for bug reports
