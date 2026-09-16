import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
