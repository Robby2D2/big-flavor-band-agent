/**
 * Tool name + measured findings -> plain-English fix-card copy. Names the
 * problem the band would hear ("Even out the tone") instead of the
 * mechanism ("Apply EQ corrections") — one mapping function per tool, since
 * each tool's findings shape is its own.
 */

export interface FixCopy {
  title: string;
  body: string;
}

function db(n: unknown, digits = 1): string {
  return typeof n === 'number' ? `${n.toFixed(digits)} dB` : '—';
}

export function fixCopyFor(
  tool: string,
  findings: Record<string, any> | undefined,
  reason: string
): FixCopy {
  const f = findings || {};
  switch (tool) {
    case 'reduce_noise':
      return {
        title: 'Take out the background noise',
        body: `Noise floor measured at ${db(f.noise_level_db)} — a steady hiss sitting under the take.`,
      };
    case 'apply_eq': {
      const n = f.adjustments?.length ?? 0;
      const fb = f.frequency_balance;
      const balance = fb
        ? ` Bass ${fb.bass_percent}% · Mid ${fb.mid_percent}% · Treble ${fb.treble_percent}%.`
        : '';
      return {
        title: 'Even out the tone',
        body: `${n} frequency imbalance${n === 1 ? '' : 's'} detected.${balance}`,
      };
    }
    case 'remove_hum':
      return {
        title: 'Remove mains hum',
        body: `Hum at ${f.fundamental_hz ?? '—'} Hz across ${f.harmonics_affected?.length ?? 0} harmonic(s).`,
      };
    case 'correct_beats':
      return {
        title: 'Tighten the timing',
        body: `${f.beats_detected ?? '—'} beats detected at ${f.detected_bpm ?? '—'} BPM (confidence ${f.mean_confidence ?? '—'}).`,
      };
    case 'trim_silence':
      return {
        title: 'Trim the silence at each end',
        body: `${Number(f.trim_start_seconds ?? 0).toFixed(1)}s of non-musical content at the start, ${Number(f.trim_end_seconds ?? 0).toFixed(1)}s at the end.`,
      };
    case 'normalize_audio':
      return {
        title: 'Even out the level',
        body: `Peak at ${db(f.current_peak_db)} — level optimization recommended.`,
      };
    case 'apply_mastering':
      return {
        title: 'Bring it to full loudness',
        body: `Measured ${f.current_lufs ?? '—'} LUFS; ~${f.estimated_gain_db ?? '—'} dB to reach the target.`,
      };
    default:
      return { title: tool, body: reason };
  }
}
