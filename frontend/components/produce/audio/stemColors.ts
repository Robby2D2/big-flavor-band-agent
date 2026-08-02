/** Per-stem accent color, matching the Console design system's stem.* tokens. */
export const STEM_COLOR: Record<string, string> = {
  // The full-mix pseudo-stem: a neutral light tone, so the parts keep the
  // saturated colors and the whole song reads as the sum of them.
  'full mix': '#c9d2e0',
  vocals: '#c56edc',
  drums: '#4da3ff',
  bass: '#3fbf88',
  other: '#e0a24a',
  guitar: '#e8607a',
  piano: '#6ee7d0',
};

export function stemColor(name: string): string {
  return STEM_COLOR[name.toLowerCase()] ?? '#8b93a1';
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: 'HIGH CONFIDENCE',
  worth_a_listen: 'WORTH A LISTEN',
};

export const CONFIDENCE_COLOR: Record<string, string> = {
  high: 'text-confirm bg-confirm/15',
  worth_a_listen: 'text-attention bg-attention/15',
};
