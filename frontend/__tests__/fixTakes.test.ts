import { describe, expect, it } from 'vitest';
import { addTake, chainSignature, ChainFix, neighbourChains, takeKey } from '@/lib/fixTakes';

const fix = (id: string, enabled: boolean, params: Record<string, any> = {}): ChainFix => ({
  id,
  tool: id,
  currentParams: params,
  enabled,
});

describe('chainSignature', () => {
  it('is empty when nothing is enabled', () => {
    expect(chainSignature([fix('a', false), fix('b', false)])).toBe('');
  });

  it('changes with the params, not only the tools', () => {
    expect(chainSignature([fix('a', true, { x: 1 })])).not.toBe(
      chainSignature([fix('a', true, { x: 2 })])
    );
  });
});

describe('neighbourChains', () => {
  const never = () => false;

  it('gives one chain per fix, each the current set with that fix flipped', () => {
    const fixes = [fix('a', true), fix('b', true), fix('c', false)];
    const chains = neighbourChains(fixes, never).map((n) => n.chain.map((s) => s.tool));
    expect(chains).toEqual([['b'], ['a'], ['a', 'b', 'c']]);
  });

  it('labels each chain with the signature the row has after that toggle', () => {
    const fixes = [fix('a', true), fix('b', true)];
    const [offA] = neighbourChains(fixes, never);
    expect(offA.signature).toBe(chainSignature([fix('a', false), fix('b', true)]));
  });

  it('leaves out the all-off state, which is the raw audio', () => {
    expect(neighbourChains([fix('a', true)], never)).toEqual([]);
  });

  it('skips a fix that cannot run yet, and keeps it out of every chain', () => {
    const fixes = [fix('a', true), fix('tempo', true), fix('b', false)];
    const incomplete = (f: ChainFix) => f.id === 'tempo';
    const chains = neighbourChains(fixes, incomplete).map((n) => n.chain.map((s) => s.tool));
    expect(chains).toEqual([['a', 'b']]);
  });
});

describe('addTake', () => {
  it('evicts the oldest take past the cap', () => {
    let takes = new Map<string, number>();
    for (const k of ['a', 'b', 'c']) takes = addTake(takes, k, 1, new Set(), 2);
    expect(Array.from(takes.keys())).toEqual(['b', 'c']);
  });

  it('never evicts a take that is playing', () => {
    let takes = new Map<string, number>();
    for (const k of ['a', 'b', 'c']) takes = addTake(takes, k, 1, new Set(['a']), 2);
    expect(Array.from(takes.keys())).toEqual(['a', 'c']);
  });

  it('keys takes by row and chain', () => {
    expect(takeKey(3, 'x')).not.toBe(takeKey(4, 'x'));
  });
});
