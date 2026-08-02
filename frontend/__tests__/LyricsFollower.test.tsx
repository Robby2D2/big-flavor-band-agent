import { beforeAll, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LyricsFollower from '@/components/LyricsFollower';
import { LyricLine } from '@/lib/lyricTimings';

const lines: LyricLine[] = [
  {
    start: 2,
    end: 5,
    text: 'Headed down south',
    words: [
      { start: 2, end: 2.5, text: 'Headed' },
      { start: 2.5, end: 3.2, text: 'down' },
      { start: 3.2, end: 5, text: 'south' },
    ],
  },
  { start: 5, end: 8, text: 'to the land of the pines' },
];

beforeAll(() => {
  // jsdom implements neither, and the component calls both on every line change.
  Element.prototype.scrollIntoView = vi.fn();
  window.matchMedia = vi.fn().mockReturnValue({ matches: false }) as any;
});

describe('LyricsFollower', () => {
  it('renders nothing without lines', () => {
    const { container } = render(<LyricsFollower lines={[]} currentTime={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('marks no line active before the first line starts', () => {
    render(<LyricsFollower lines={lines} currentTime={0} />);
    expect(screen.getByTestId('lyric-line-0')).not.toHaveAttribute('data-active');
    expect(screen.getByTestId('lyric-line-1')).not.toHaveAttribute('data-active');
  });

  it('highlights the line being sung', () => {
    render(<LyricsFollower lines={lines} currentTime={6} />);
    expect(screen.getByTestId('lyric-line-0')).not.toHaveAttribute('data-active');
    expect(screen.getByTestId('lyric-line-1')).toHaveAttribute('data-active');
  });

  it('highlights the word being sung on the active line', () => {
    render(<LyricsFollower lines={lines} currentTime={2.6} />);
    expect(screen.getByTestId('lyric-word-active')).toHaveTextContent('down');
  });

  it('moves the word highlight as time advances', () => {
    const { rerender } = render(<LyricsFollower lines={lines} currentTime={2.1} />);
    expect(screen.getByTestId('lyric-word-active')).toHaveTextContent('Headed');

    rerender(<LyricsFollower lines={lines} currentTime={4} />);
    expect(screen.getByTestId('lyric-word-active')).toHaveTextContent('south');
  });

  it('falls back to plain text on a line with no word timings', () => {
    render(<LyricsFollower lines={lines} currentTime={6} />);
    const active = screen.getByTestId('lyric-line-1');
    expect(active).toHaveTextContent('to the land of the pines');
    expect(screen.queryByTestId('lyric-word-active')).toBeNull();
  });

  it('scrolls the active line into view', () => {
    render(<LyricsFollower lines={lines} currentTime={6} />);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it('seeks to a line start when a line is clicked', async () => {
    const onSeek = vi.fn();
    render(<LyricsFollower lines={lines} currentTime={0} onSeek={onSeek} />);

    await userEvent.click(screen.getByTestId('lyric-line-1'));
    expect(onSeek).toHaveBeenCalledWith(5);
  });

  it('does not make lines clickable without onSeek', async () => {
    render(<LyricsFollower lines={lines} currentTime={0} />);
    // No handler to assert on; the point is that clicking is inert, not a crash.
    await userEvent.click(screen.getByTestId('lyric-line-1'));
    expect(screen.getByTestId('lyric-line-1')).not.toHaveClass('cursor-pointer');
  });
});
