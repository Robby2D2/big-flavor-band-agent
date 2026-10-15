import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RadioLyrics from '@/components/RadioLyrics';
import { LyricTimings } from '@/lib/lyricTimings';

const timings: LyricTimings = {
  format_version: 1,
  source: 'whisper',
  model: null,
  audio_source: null,
  status: 'current',
  lines: [
    { start: 2, end: 5, text: 'Headed down south' },
    { start: 5, end: 8, text: 'to the land of the pines' },
  ],
};

function mockLyrics(body: object | null, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }) as any;
}

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as any;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RadioLyrics', () => {
  it('follows along at the polled position when the song has timings', async () => {
    mockLyrics({ song_id: 7, lyrics: 'Headed down south', timings });
    render(<RadioLyrics songId={7} position={6} playing={false} />);

    const line = await screen.findByTestId('lyric-line-1');
    expect(line).toHaveAttribute('data-active');
    expect(global.fetch).toHaveBeenCalledWith('/api/songs/7/lyrics/timed');
  });

  it('shows plain lyrics when the timings are stale', async () => {
    mockLyrics({
      song_id: 7,
      lyrics: 'Hand-edited words',
      timings: { ...timings, status: 'stale' },
    });
    render(<RadioLyrics songId={7} position={6} playing={false} />);

    expect(await screen.findByText('Hand-edited words')).toBeInTheDocument();
    expect(screen.queryByTestId('lyric-line-0')).not.toBeInTheDocument();
  });

  it('says so when the song has no lyrics', async () => {
    mockLyrics({ song_id: 7, lyrics: '', timings: null });
    render(<RadioLyrics songId={7} position={0} playing />);

    expect(await screen.findByText('No lyrics for this song.')).toBeInTheDocument();
  });

  it('says so when the lyrics cannot be loaded', async () => {
    mockLyrics({ error: 'boom' }, 500);
    render(<RadioLyrics songId={7} position={0} playing />);

    expect(
      await screen.findByText('Could not load the lyrics for this song.')
    ).toBeInTheDocument();
  });
});
