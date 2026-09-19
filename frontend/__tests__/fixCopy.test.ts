import { describe, expect, it } from 'vitest';
import { fixCopyFor, fixTitleFor, manualFixCopy } from '@/components/produce/audio/fixCopy';

describe('fix card copy', () => {
  it('titles a tool the same way wherever it is named', () => {
    // The picker lists this, the card it creates is headed with it — the same
    // call, so the two can never drift apart.
    expect(fixTitleFor('apply_eq')).toBe('Even out the tone');
    expect(manualFixCopy('apply_eq', 'Shape the sound with EQ.').title).toBe('Even out the tone');
  });

  it('falls back to the tool summary, then its name, for an untitled tool', () => {
    expect(fixTitleFor('brand_new_tool', 'Do a new thing.')).toBe('Do a new thing.');
    expect(fixTitleFor('brand_new_tool')).toBe('brand_new_tool');
    expect(manualFixCopy('brand_new_tool', 'Do a new thing.').title).toBe('Do a new thing.');
  });

  it('tells a producer adding hum removal to pick a mains frequency', () => {
    // Added at its defaults the tool re-runs the detection that already found
    // no hum and copies the file, so "Hear it" would sound like nothing
    // happened unless the card says what to set.
    const body = manualFixCopy('remove_hum').body;
    expect(body).toContain('50 or 60 Hz');
    expect(body).toContain('Adjust');
  });

  it('titles pitch, clicks and tempo the same however they reach the queue', () => {
    // Pitch and clicks are measured now, so their cards can arrive either way;
    // match_tempo is still picker-only, deliberately.
    expect(fixTitleFor('correct_pitch')).toBe('Pull the notes to pitch');
    expect(fixTitleFor('remove_artifacts')).toBe('Clean up clicks and pops');
    expect(fixTitleFor('match_tempo')).toBe('Stretch it to a target tempo');
    expect(fixCopyFor('correct_pitch', {}, '').title).toBe(fixTitleFor('correct_pitch'));
  });

  it('puts the measured numbers in a recommended pitch card', () => {
    const body = fixCopyFor(
      'correct_pitch',
      { notes_detected: 46, notes_off_target: 17, median_deviation_cents: 30.4, key: 'A minor' },
      'measured'
    ).body;
    expect(body).toContain('17 of 46 notes');
    expect(body).toContain('30 cents');
    expect(body).toContain('A minor');
  });

  it('says which scope a clicks card is repairing', () => {
    // One physical click lands in a stem *and* in the mix those stems sum to,
    // so a producer has to be able to tell the two cards apart.
    const findings = { count: 4, per_minute: 1.2 };
    expect(fixCopyFor('remove_artifacts', findings, '', 'stem').body).toContain('in this stem');
    expect(fixCopyFor('remove_artifacts', findings, '', 'master').body).toContain(
      'in the whole mix'
    );
    expect(fixCopyFor('remove_artifacts', findings, '', 'stem').body).toContain('4 clicks');
  });

  it('keeps a one-click card out of the plural', () => {
    expect(fixCopyFor('remove_artifacts', { count: 1, per_minute: 0.3 }, '').body).toContain(
      '1 click/pop'
    );
  });

  it('tells a producer adding match_tempo that the BPM has no default', () => {
    expect(manualFixCopy('match_tempo', undefined, 'master').body).toContain('target BPM');
  });

  it('names the measured tempo a seeded card already carries', () => {
    // Seeded from the song's own analysis, the card is runnable on arrival —
    // telling the producer to go and set a value that is already there would
    // be wrong.
    const body = manualFixCopy('match_tempo', undefined, 'master', { target_bpm: 118.5 }).body;
    expect(body).toContain('118.5 BPM');
    expect(body).not.toContain('Set the target BPM');
  });

  it('warns about drift only when match_tempo is added to a single stem', () => {
    // On one stem it stretches that stem alone; on the full mix there is
    // nothing for it to drift against.
    expect(manualFixCopy('match_tempo', undefined, 'stem').body).toContain('drift apart');
    expect(manualFixCopy('match_tempo', undefined, 'master').body).not.toContain('drift apart');
  });

  it('says a pitch card starts in auto-tune', () => {
    expect(manualFixCopy('correct_pitch').body).toContain('auto-tune');
  });

  it('points every other added fix at the drawer for its amount', () => {
    expect(manualFixCopy('apply_mastering').body).toBe(
      "You added this — the analysis didn't flag it. Set the amount under Adjust."
    );
  });
});
