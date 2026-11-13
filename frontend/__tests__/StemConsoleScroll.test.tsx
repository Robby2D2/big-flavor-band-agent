import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import StemConsole from '@/components/produce/audio/StemConsole';
import FixCard from '@/components/produce/audio/FixCard';
import type { FixEntry, StemInfo } from '@/hooks/useProcessingQueue';
import { FULL_MIX_STEM_ID } from '@/hooks/useProcessingQueue';

// The waveform draws to a canvas jsdom has no 2D context for, and nothing here
// is about drawing — the rows' geometry is.
vi.mock('@/components/produce/WaveformView', () => ({
  default: () => <div data-testid="waveform" />,
}));

const stems: StemInfo[] = [
  { id: FULL_MIX_STEM_ID, name: 'full mix', displayName: null, instruments: [], silent: false, tagged: true },
  { id: 901, name: 'vocals', displayName: null, instruments: [], silent: false, tagged: true },
  { id: 902, name: 'drums', displayName: null, instruments: [], silent: false, tagged: true },
];

const consoleProps = {
  stems,
  peaks: {},
  peaksLoadingIds: new Set<number>(),
  controls: {},
  setControl: vi.fn(),
  selectedStemId: 901,
  onSelectStem: vi.fn(),
  fixesForStem: () => [] as FixEntry[],
  analyzedStemIds: new Set<number>(),
  analyzingStemIds: new Set<number>(),
  onAnalyzeStem: vi.fn(),
  identifyingStemIds: new Set<number>(),
  onIdentifyStem: vi.fn(),
  onRenameStem: vi.fn(),
  playhead: 0,
  maxDuration: 120,
  onSeek: vi.fn(),
  separating: false,
  analyzed: true,
  analysisNote: null,
};

const scrollRegion = () => screen.getByTestId('stem-rows-scroll');

describe('the stem console contains its own sideways scroll', () => {
  it('puts every row inside a horizontally scrollable region', () => {
    render(<StemConsole {...consoleProps} />);

    const region = scrollRegion();
    expect(region.className).toContain('overflow-x-auto');
    // A row is wider than a phone by design (fixed name and meter columns), so
    // what matters is that the overflow is caught here rather than by the page.
    for (const label of ['full mix', 'vocals', 'drums']) {
      expect(region).toContainElement(screen.getByText(label));
    }
  });

  it('carries no player of its own — Play lives in the bar above the console', () => {
    render(<StemConsole {...consoleProps} />);

    expect(screen.queryByRole('button', { name: 'Play' })).toBeNull();
  });

  it('holds the scrolled rows open to the full row width', () => {
    // Without a minimum the row backgrounds would stop at the viewport edge and
    // the scrolled-to part of the console would render on bare panel.
    render(<StemConsole {...consoleProps} />);

    expect(scrollRegion().firstElementChild?.className).toContain('min-w-[40rem]');
  });

  it('does not reflow the row itself — the columns stay fixed at every width', () => {
    // Option 2 was explicitly rejected: cross-row column alignment is the
    // console's value, so no breakpoint may restyle the row.
    const { container } = render(<StemConsole {...consoleProps} />);

    const rowClasses = Array.from(container.querySelectorAll('[class*="w-44"]')).map(
      (el) => el.parentElement?.className ?? ''
    );
    expect(rowClasses.length).toBe(stems.length);
    for (const className of rowClasses) {
      expect(className).not.toMatch(/\b(sm|md|lg):/);
    }
  });
});

const fix: FixEntry = {
  id: 'stem:901:reduce_noise',
  scope: 'stem',
  stemId: 901,
  tool: 'reduce_noise',
  title: 'Take out the background noise',
  body: 'Noise floor measured at -44.0 dB.',
  confidence: 'high',
  reason: 'measured',
  findings: {},
  suggestedParams: {},
  currentParams: {},
  enabled: true,
  source: 'manual',
};

describe('fix card buttons are thumb-sized on a phone', () => {
  it('gives Adjust and Remove a 44px floor that lifts on desktop', () => {
    render(
      <FixCard
        fix={fix}
        index={0}
        onToggle={vi.fn()}
        onAdjust={vi.fn()}
        onRemove={vi.fn()}
      />
    );

    for (const name of ['Adjust', 'Remove']) {
      const button = screen.getByRole('button', { name });
      expect(button.className).toContain('min-h-[44px]');
      expect(button.className).toContain('sm:min-h-0');
      // The target grows, not the type — the card's density is the point.
      expect(button.className).toContain('text-xs');
    }
  });
});

describe('a row opens to its own fixes', () => {
  it('shows the fix list beneath the open row only', () => {
    render(
      <StemConsole {...consoleProps} renderFixes={(stem) => <p>fixes for {stem.name}</p>} />
    );

    expect(screen.getByText('fixes for vocals')).toBeInTheDocument();
    expect(screen.queryByText('fixes for drums')).toBeNull();
    expect(screen.queryByText('fixes for full mix')).toBeNull();
  });

  it('closes the open row when it is clicked again, and opens another', () => {
    const onSelectStem = vi.fn();
    render(<StemConsole {...consoleProps} onSelectStem={onSelectStem} />);

    fireEvent.click(screen.getByText('vocals'));
    expect(onSelectStem).toHaveBeenLastCalledWith(null);
    fireEvent.click(screen.getByText('drums'));
    expect(onSelectStem).toHaveBeenLastCalledWith(902);
  });

  it('turns a row with any fix on all off, without opening or closing it', () => {
    const onSelectStem = vi.fn();
    const onSetRowFixesEnabled = vi.fn();
    const drumFixes: FixEntry[] = [
      { ...fix, id: 'stem:902:a', stemId: 902, enabled: true },
      { ...fix, id: 'stem:902:b', stemId: 902, enabled: false },
    ];
    render(
      <StemConsole
        {...consoleProps}
        onSelectStem={onSelectStem}
        fixesForStem={(id) => (id === 902 ? drumFixes : [])}
        onSetRowFixesEnabled={onSetRowFixesEnabled}
      />
    );

    const toggle = screen.getByRole('switch', { name: 'All fixes on drums' });
    expect(toggle).toHaveTextContent('1/2');
    fireEvent.click(toggle);
    expect(onSetRowFixesEnabled).toHaveBeenCalledWith(902, false);
    expect(onSelectStem).not.toHaveBeenCalled();
    // Rows with nothing to switch carry no switch.
    expect(screen.queryByRole('switch', { name: 'All fixes on vocals' })).toBeNull();
  });
});
