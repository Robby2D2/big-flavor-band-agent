import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ResultSidebar from '@/components/produce/audio/ResultSidebar';

const props = {
  enabledCount: 17,
  totalCount: 17,
  onAcceptAll: vi.fn(async () => ({})),
  onPreviewFull: vi.fn(async () => '/tmp/mix.wav'),
  onAccepted: vi.fn(),
};

const button = (name: RegExp) => screen.getByRole('button', { name });

describe('ResultSidebar while a render is in flight', () => {
  it('offers both actions when nothing is rendering', () => {
    render(<ResultSidebar {...props} />);

    expect(button(/Accept all & save version/)).toBeEnabled();
    expect(button(/Preview full mix first/)).toBeEnabled();
  });

  it('disables both, so a second render cannot be queued behind the first', () => {
    render(<ResultSidebar {...props} renderInProgress />);

    expect(button(/Accept all & save version/)).toBeDisabled();
    expect(button(/Preview full mix first/)).toBeDisabled();
  });

  it('still disables them when no fix is enabled', () => {
    render(<ResultSidebar {...props} enabledCount={0} />);

    expect(button(/Accept all & save version/)).toBeDisabled();
  });
});

describe('ResultSidebar and what a render had to say', () => {
  const notice = {
    scope: 'drums',
    tool: 'correct_pitch',
    reason: 'Input does not look like a single line; applied a whole-file shift instead.',
  };

  it('shows what a preview reported — a preview waits for its render', async () => {
    render(
      <ResultSidebar
        {...props}
        onPreviewFull={vi.fn(async () => ({ path: '/tmp/mix.wav', notices: [notice] }))}
      />
    );

    await userEvent.click(button(/Preview full mix first/));

    await waitFor(() => expect(screen.getByText(/did less than it said/)).toBeInTheDocument());
    expect(screen.getByText(notice.reason)).toBeInTheDocument();
  });

  // Saving hands the render to a background job, so the response it returns is
  // seeded with an empty notice list whenever the mix is not already cached.
  // Reading notices off it is what silently dropped the one warning this whole
  // path exists to deliver (#91) — the page reports a save instead.
  it('claims nothing about a save whose render has barely started', async () => {
    render(
      <ResultSidebar
        {...props}
        onAcceptAll={vi.fn(async () => undefined)}
      />
    );

    await userEvent.click(button(/Accept all & save version/));

    await waitFor(() => expect(screen.getByText(/Saved as a new version/)).toBeInTheDocument());
    expect(screen.queryByText(/did less than it said/)).not.toBeInTheDocument();
    expect(screen.queryByText(/did less than they said/)).not.toBeInTheDocument();
  });
});
