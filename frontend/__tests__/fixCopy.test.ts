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

  it('points every other added fix at the drawer for its amount', () => {
    expect(manualFixCopy('apply_mastering').body).toBe(
      "You added this — the analysis didn't flag it. Set the amount under Adjust."
    );
  });
});
