import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import TransportBar from '@/components/produce/audio/TransportBar';

vi.mock('@/components/produce/WaveformView', () => ({
  default: () => <div data-testid="waveform" />,
}));

const props = {
  peaks: null,
  peaksLoading: false,
  playbackReady: true,
  playing: false,
  playhead: 0,
  maxDuration: 120,
  onTogglePlay: vi.fn(),
  onSeek: vi.fn(),
  auditionRendering: false,
  audition: null,
  unrenderedRows: [] as string[],
  renderingFixes: false,
  withFixes: false,
};

describe('TransportBar', () => {
  it('keeps Play enabled while fixes render, and says the original is playing', () => {
    render(<TransportBar {...props} unrenderedRows={['vocals', 'drums']} renderingFixes />);

    expect(screen.getByRole('button', { name: 'Play' })).toBeEnabled();
    expect(screen.getByTestId('transport-hearing')).toHaveTextContent(
      'Original audio on vocals, drums · fixes rendering…'
    );
  });

  it('says when fixes are not rendered and nothing is rendering them', () => {
    render(<TransportBar {...props} unrenderedRows={['vocals']} />);

    expect(screen.getByTestId('transport-hearing')).toHaveTextContent('fixes not rendered yet');
  });

  it('says so once everything audible plays with its fixes', () => {
    render(<TransportBar {...props} withFixes />);

    expect(screen.getByTestId('transport-hearing')).toHaveTextContent('With fixes');
  });

  it('waits only for Hear it, which is about hearing that one fix', () => {
    render(<TransportBar {...props} auditionRendering />);

    expect(screen.getByRole('button', { name: 'Rendering fix' })).toBeDisabled();
  });

  it('waits for audio to decode before it can play anything', () => {
    render(<TransportBar {...props} playbackReady={false} />);

    expect(screen.getByRole('button', { name: 'Preparing playback' })).toBeDisabled();
  });
});
