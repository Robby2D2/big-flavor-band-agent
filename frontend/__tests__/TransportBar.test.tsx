import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import TransportBar from '@/components/produce/audio/TransportBar';

vi.mock('@/components/produce/WaveformView', () => ({
  default: () => <div data-testid="waveform" />,
}));

const props = {
  peaks: null,
  peaksLoading: false,
  playbackReady: true,
  audioLoading: null,
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
  songId: 7,
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

  it('shows how much audio has downloaded while it waits', () => {
    render(
      <TransportBar
        {...props}
        playbackReady={false}
        audioLoading={{ ready: 0, total: 6, fraction: 0.425 }}
      />
    );

    expect(screen.getByTestId('transport-hearing')).toHaveTextContent(
      'Loading audio 42% · 0 of 6 parts ready'
    );
  });

  it('says it is decoding once every byte is in', () => {
    render(<TransportBar {...props} audioLoading={{ ready: 2, total: 6, fraction: 1 }} />);

    expect(screen.getByTestId('transport-hearing')).toHaveTextContent(
      'Decoding audio · 2 of 6 parts ready'
    );
  });

  it('counts parts alone when the server sent no sizes', () => {
    render(<TransportBar {...props} audioLoading={{ ready: 2, total: 6, fraction: null }} />);

    expect(screen.getByTestId('transport-hearing')).toHaveTextContent(
      'Loading audio · 2 of 6 parts ready'
    );
  });

  describe('Lyrics toggle', () => {
    const timedResponse = (timings: unknown) =>
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ song_id: 7, lyrics: '', timings }) });

    it('fetches the song timings on open and follows the playhead', async () => {
      Element.prototype.scrollIntoView = vi.fn();
      const fetchMock = timedResponse({
        format_version: 1, source: null, model: null, audio_source: null, status: 'current',
        lines: [
          { start: 0, end: 5, text: 'Buckets of rain' },
          { start: 5, end: 10, text: 'Buckets of tears' },
        ],
      });
      vi.stubGlobal('fetch', fetchMock);

      render(<TransportBar {...props} playhead={6} />);
      fireEvent.click(screen.getByRole('button', { name: 'Lyrics' }));

      expect(await screen.findByTestId('lyric-line-1')).toHaveAttribute('data-active', 'true');
      expect(fetchMock).toHaveBeenCalledWith('/api/songs/7/lyrics/timed');
      vi.unstubAllGlobals();
    });

    it('says to re-extract when the timings are stale', async () => {
      vi.stubGlobal(
        'fetch',
        timedResponse({
          format_version: 1, source: null, model: null, audio_source: null, status: 'stale',
          lines: [{ start: 0, end: 5, text: 'x' }],
        })
      );

      render(<TransportBar {...props} />);
      fireEvent.click(screen.getByRole('button', { name: 'Lyrics' }));

      expect(await screen.findByText(/re-extract to follow along/)).toBeInTheDocument();
      vi.unstubAllGlobals();
    });
  });
});
