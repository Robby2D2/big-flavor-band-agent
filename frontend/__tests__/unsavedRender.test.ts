import { describe, expect, it } from 'vitest';
import {
  UNSAVED_VERSION_ID,
  unsavedRenderAudioUrl,
  unsavedRenderFrom,
  unsavedRenderLabel,
} from '@/lib/unsavedRender';

describe('unsavedRenderFrom', () => {
  it('returns the mix a finished preview render left behind', () => {
    const render = unsavedRenderFrom({
      status: 'complete',
      preview: true,
      fix_count: 17,
      candidate_path: '/app/produced/880/accept_fixes/1/master.wav',
    } as never);

    expect(render?.candidatePath).toBe('/app/produced/880/accept_fixes/1/master.wav');
    expect(render?.fixCount).toBe(17);
  });

  it('ignores a finished save — that became a real version', () => {
    expect(
      unsavedRenderFrom({
        status: 'complete',
        preview: false,
        version: { version_id: 7, is_published: false },
      } as never)
    ).toBeNull();
  });

  it('ignores a render that is still going', () => {
    expect(unsavedRenderFrom({ status: 'running', preview: true } as never)).toBeNull();
  });

  it('ignores a failed render', () => {
    expect(unsavedRenderFrom({ status: 'failed', preview: true } as never)).toBeNull();
  });

  it('ignores an idle song', () => {
    expect(unsavedRenderFrom({ status: 'idle' } as never)).toBeNull();
  });

  it('needs a file to play — no path, no row', () => {
    expect(unsavedRenderFrom({ status: 'complete', preview: true } as never)).toBeNull();
  });
});

describe('the pseudo-row id', () => {
  it('cannot collide with a real version id', () => {
    expect(UNSAVED_VERSION_ID).toBeLessThan(0);
  });
});

describe('unsavedRenderAudioUrl', () => {
  it('streams the candidate by path, since it has no version id', () => {
    expect(unsavedRenderAudioUrl('/app/produced/a b.wav')).toBe(
      '/api/produce/clean/preview?path=%2Fapp%2Fproduced%2Fa%20b.wav'
    );
  });

  it('escapes a path that would otherwise break the query string', () => {
    expect(unsavedRenderAudioUrl('/x/y&z=1.wav')).toContain('%26z%3D1');
  });
});

describe('unsavedRenderLabel', () => {
  it('says what was applied and that it is not kept yet', () => {
    const label = unsavedRenderLabel({ candidatePath: '/x', fixCount: 17, renderedAt: null });
    expect(label).toContain('17 fixes');
    expect(label).toContain('not saved');
  });

  it('counts one fix in the singular', () => {
    const label = unsavedRenderLabel({ candidatePath: '/x', fixCount: 1, renderedAt: null });
    expect(label).toContain('1 fix ');
    expect(label).not.toContain('1 fixes');
  });
});
