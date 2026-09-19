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
  onHear: vi.fn(),
};

const hearButton = () => screen.getByRole('button', { name: /Hear it|Playing|Rendering/ });

describe('auditioning a fix', () => {
  it('never renders a player of its own', () => {
    // The whole point of the change: one transport for the page, so a fix is
    // judged in the mix rather than as a disconnected clip.
    const { container } = render(<FixCard {...props} />);
    expect(container.querySelector('audio')).toBeNull();
  });

  it('hands Hear it to the transport instead of fetching a clip', async () => {
    const onHear = vi.fn();
    render(<FixCard {...props} onHear={onHear} />);

    await userEvent.click(hearButton());
    expect(onHear).toHaveBeenCalledTimes(1);
  });

  it('is unavailable, not dead, until the console has audio', () => {
    render(<FixCard {...props} canHear={false} />);
    expect(hearButton()).toBeDisabled();
  });

  it('says which card the transport is on', () => {
    render(<FixCard {...props} auditioning />);

    expect(screen.getByText('ON THE TRANSPORT')).toBeInTheDocument();
    expect(hearButton()).toHaveTextContent('Playing');
  });

  it('shows the pending state while its chain renders', () => {
    render(<FixCard {...props} auditioning rendering />);

    expect(hearButton()).toHaveTextContent('Rendering…');
    expect(hearButton()).toBeDisabled();
  });

  it('refuses to audition a card that is still missing a required setting', () => {
    render(
      <FixCard
        {...props}
        missingParams={[
          { name: 'target_bpm', type: 'number', default: null, min: null, max: null,
            label: 'Target BPM', help: null, required: true, choices: null },
        ]}
      />
    );

    expect(hearButton()).toBeDisabled();
    expect(screen.getByText(/Needs Target BPM/)).toBeInTheDocument();
  });
});
