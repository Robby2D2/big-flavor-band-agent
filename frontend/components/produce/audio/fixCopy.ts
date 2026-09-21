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
  correct_pitch: 'Pull the notes to pitch',
  remove_artifacts: 'Clean up clicks and pops',
  // The one left with no analyze() of its own — deliberately, since there is no
  // *correct* BPM for a song — so the picker is the only place it appears.
  match_tempo: 'Stretch it to a target tempo',
};

/**
 * The card title for a tool — also what the "add a fix" picker lists it as, so
 * the option you choose and the card you get read the same. `fallback` is the
 * tool's own one-line summary, for a tool that has no friendly title yet.
 */
export function fixTitleFor(tool: string, fallback?: string): string {
  return FIX_TITLES[tool] ?? fallback ?? tool;
}

function db(n: unknown, digits = 1): string {
  return typeof n === 'number' ? `${n.toFixed(digits)} dB` : '—';
}

export function fixCopyFor(
  tool: string,
  findings: Record<string, any> | undefined,
  reason: string,
  scope: 'stem' | 'master' = 'stem'
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
    case 'correct_pitch': {
      // The counts come from the loudest window, not the whole stem — pyin over
      // a full file is far too slow to run per row. Saying so keeps "15 of 46"
      // from reading as a whole-song tally.
      const measuredIn = f.analyzed_seconds
        ? `the loudest ${Math.round(f.analyzed_seconds)} seconds`
        : 'the part measured';
      return {
        title,
        body:
          `${f.notes_off_target ?? '—'} of ${f.notes_detected ?? '—'} notes in ${measuredIn} sit ` +
          `noticeably off pitch (median ${Math.round(f.median_deviation_cents ?? 0)} cents), in ` +
          `${f.key ?? 'an undetermined key'}. Auto-tune is pre-set to pull every note onto its ` +
          `nearest semitone — the same target these numbers are measured against.`,
      };
    }
    case 'remove_artifacts': {
      const n = f.count ?? 0;
      // The same physical click lands in a stem *and* in the mix those stems
      // sum to, so each card says which one it is repairing — otherwise it
      // reads as two problems and gets fixed twice.
      const where = scope === 'master' ? 'in the whole mix' : 'in this stem';
      return {
        title,
        body: `${n} click${n === 1 ? '' : 's'}/pop${n === 1 ? '' : 's'} ${where} (${
          f.per_minute ?? '—'
        } per minute) — sharp jumps the music itself doesn't make.`,
      };
    }
    default:
      return { title, body: reason };
  }
}

/**
 * Tools whose declared defaults leave the audio untouched, so a card added at
 * those defaults renders nothing until the producer sets something.
 *
 * Only `remove_hum` is in this position: its one param has no default, and with
 * no mains frequency given, apply re-runs the same detection that already found
 * no hum and copies the file. Every other tool here starts from defaults that
 * do real work. Saying so on the card keeps "Hear it" from sounding broken.
 */
const MANUAL_SETUP_HINTS: Record<string, string> = {
  remove_hum:
    "You added this — the analysis didn't flag it. Pick 50 or 60 Hz under Adjust: " +
    'with no mains frequency set it just re-runs the detection that already heard no hum.',
  match_tempo:
    'You added this. Set the target BPM under Adjust — nothing measured a tempo for ' +
    'this row, and the whole track is stretched to whatever you choose.',
};

/**
 * Per-tool notes for a hand-added card, appended to the body.
 *
 * Only where a producer could reasonably be surprised by what the tool does to
 * the rest of the session — not a second description of the tool.
 */
const MANUAL_SCOPE_NOTES: Record<string, string> = {
  match_tempo:
    ' On a single stem this stretches that stem alone, so give every stem the same ' +
    'target or they will drift apart.',
  correct_pitch:
    ' Starts in auto-tune, pulling each note to the nearest one in the key; ' +
    'switch to a plain transpose under Adjust.',
};

/**
 * Copy for a fix the producer added themselves. There are no measurements to
 * report — the whole point is that the analysis didn't flag it — so the body
 * says where the card came from and points at where the amount is set.
 */
export function manualFixCopy(
  tool: string,
  summary?: string,
  scope?: 'stem' | 'master',
  /** The params the card is starting from, so the copy can name a real number. */
  params: Record<string, any> = {}
): FixCopy {
  // A tempo card seeded from the song's own measured BPM is a different card
  // from one that has nothing to start from, and should not tell the producer
  // to go and set a value that is already there.
  const base =
    tool === 'match_tempo' && params.target_bpm != null
      ? `You added this. Starts at the ${params.target_bpm} BPM measured for this row — ` +
        'change it under Adjust to stretch the performance anywhere you want.'
      : MANUAL_SETUP_HINTS[tool] ??
        "You added this — the analysis didn't flag it. Set the amount under Adjust.";
  // The stretch warning is only true of a stem; the full mix has nothing to
  // drift against.
  const note =
    tool === 'match_tempo' && scope !== 'stem' ? '' : MANUAL_SCOPE_NOTES[tool] ?? '';
  return { title: fixTitleFor(tool, summary), body: base + note };
}
