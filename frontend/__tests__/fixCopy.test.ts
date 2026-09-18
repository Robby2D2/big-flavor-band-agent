import { describe, expect, it } from 'vitest';
import { fixTitleFor, manualFixCopy } from '@/components/produce/audio/fixCopy';

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

  it('names the three tools no analyzer can ever recommend', () => {
    // Nothing in the backend produces a recommendation for these, so the card
    // title comes from here or it comes from the raw tool name.
    expect(fixTitleFor('correct_pitch')).toBe('Pull the notes to pitch');
    expect(fixTitleFor('remove_artifacts')).toBe('Clean up clicks and pops');
    expect(fixTitleFor('match_tempo')).toBe('Stretch it to a target tempo');
  });

  it('tells a producer adding match_tempo that the BPM has no default', () => {
    expect(manualFixCopy('match_tempo', undefined, 'master').body).toContain('target BPM');
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
