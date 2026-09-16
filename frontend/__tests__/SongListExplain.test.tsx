import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SongList from '@/components/SongList';

const song = {
  id: 1299,
  title: 'Middle of the night',
  genre: 'pop',
  mood: 'melancholic',
  energy: 'high',
  max_similarity: 0.64,
};

const renderList = () =>
  render(
    <SongList
      songs={[song]}
      onPlay={vi.fn()}
      query="upbeat country song about home"
    />
  );

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the "why did this match" explanation', () => {
  it('shows a busy indicator while the answer is being worked out', async () => {
    // A request that never settles: the UI must say it is thinking, not sit blank.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    renderList();
    await userEvent.click(screen.getByTitle('Why this matched'));

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument();
    });
    expect(screen.getByText(/Working out why/)).toBeInTheDocument();
  });

  it('marks the control itself busy, not just the popover', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));

    renderList();
    await userEvent.click(screen.getByTitle('Why this matched'));

    await waitFor(() => {
      expect(screen.getByTitle('Working out why…')).toHaveAttribute('aria-busy', 'true');
    });
  });

  it('replaces the indicator with the reason once it arrives', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ reason: 'It is about going home.' })))
    );

    renderList();
    await userEvent.click(screen.getByTitle('Why this matched'));

    expect(await screen.findByText('It is about going home.')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('shows the failure rather than spinning forever', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ error: 'Could not explain' }), { status: 502 }))
    );

    renderList();
    await userEvent.click(screen.getByTitle('Why this matched'));

    expect(await screen.findByText('Could not explain')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
