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

/**
 * What each tool is called on a card. Shared by the measured copy below and by
 * producer-added fixes, which have no findings to describe but are the same
 * job — a card should read the same whether the analysis proposed it or the
 * producer did.
 */
const FIX_TITLES: Record<string, string> = {
  reduce_noise: 'Take out the background noise',
  apply_eq: 'Even out the tone',
  remove_hum: 'Remove mains hum',
  correct_beats: 'Tighten the timing',
  trim_silence: 'Trim the silence at each end',
  normalize_audio: 'Even out the level',
  apply_mastering: 'Bring it to full loudness',
};

/** The card title for a tool, falling back to the tool's own name. */
export function fixTitleFor(tool: string): string {
  return FIX_TITLES[tool] ?? tool;
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
  const title = fixTitleFor(tool);
  switch (tool) {
    case 'reduce_noise':
      return {
        title,
        body: `Noise floor measured at ${db(f.noise_level_db)} — a steady hiss sitting under the take.`,
      };
    case 'apply_eq': {
      const n = f.adjustments?.length ?? 0;
      const fb = f.frequency_balance;
      const balance = fb
        ? ` Bass ${fb.bass_percent}% · Mid ${fb.mid_percent}% · Treble ${fb.treble_percent}%.`
        : '';
      return {
        title,
        body: `${n} frequency imbalance${n === 1 ? '' : 's'} detected.${balance}`,
      };
    }
    case 'remove_hum':
      return {
        title,
        body: `Hum at ${f.fundamental_hz ?? '—'} Hz across ${f.harmonics_affected?.length ?? 0} harmonic(s).`,
      };
    case 'correct_beats':
      return {
        title,
        body: `${f.beats_detected ?? '—'} beats detected at ${f.detected_bpm ?? '—'} BPM (confidence ${f.mean_confidence ?? '—'}).`,
      };
    case 'trim_silence':
      return {
        title,
        body: `${Number(f.trim_start_seconds ?? 0).toFixed(1)}s of non-musical content at the start, ${Number(f.trim_end_seconds ?? 0).toFixed(1)}s at the end.`,
      };
    case 'normalize_audio':
      return {
        title,
        body: `Peak at ${db(f.current_peak_db)} — level optimization recommended.`,
      };
    case 'apply_mastering':
      return {
        title,
        body: `Measured ${f.current_lufs ?? '—'} LUFS; ~${f.estimated_gain_db ?? '—'} dB to reach the target.`,
      };
    default:
      return { title, body: reason };
  }
}

/**
 * Copy for a fix the producer added themselves. There are no measurements to
 * report — the whole point is that the analysis didn't flag it — so the body
 * says where the card came from and points at where the amount is set.
 */
export function manualFixCopy(tool: string, summary?: string): FixCopy {
  return {
    title: FIX_TITLES[tool] ?? summary ?? tool,
    body: "You added this — the analysis didn't flag it. Set the amount under Adjust.",
  };
}
