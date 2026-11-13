import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FixCard from '@/components/produce/audio/FixCard';
import type { FixEntry } from '@/hooks/useProcessingQueue';

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
  source: 'analysis',
};

const props = {
  fix,
  index: 0,
  onToggle: vi.fn(),
  onAdjust: vi.fn(),
};

describe('hearing a fix', () => {
  it('never renders a player of its own', () => {
    // One transport for the page, so a fix is judged in the mix rather than as
    // a disconnected clip.
    const { container } = render(<FixCard {...props} />);
    expect(container.querySelector('audio')).toBeNull();
  });

  it('has no play button: the song plays from the transport and the switch A/Bs it', () => {
    render(<FixCard {...props} />);

    expect(screen.queryByRole('button', { name: /Hear it/ })).toBeNull();
  });

  it('switches the fix from its toggle', async () => {
    const onToggle = vi.fn();
    render(<FixCard {...props} onToggle={onToggle} />);

    await userEvent.click(screen.getByRole('button', { name: 'Turn this fix off' }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('will not switch on a card that is still missing a required setting', () => {
    render(
      <FixCard
        {...props}
        missingParams={[
          { name: 'target_bpm', type: 'number', default: null, min: null, max: null,
            label: 'Target BPM', help: null, required: true, choices: null },
        ]}
      />
    );

    expect(
      screen.getByRole('button', { name: 'Set the missing setting under Adjust before turning this on' })
    ).toBeDisabled();
    expect(screen.getByText(/Needs Target BPM/)).toBeInTheDocument();
  });
});
