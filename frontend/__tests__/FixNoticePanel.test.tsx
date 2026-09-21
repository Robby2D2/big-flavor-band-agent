import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import FixNoticePanel from '@/components/produce/audio/FixNoticePanel';

const notice = (scope: string) => ({
  scope,
  tool: 'correct_pitch',
  reason: `${scope}: applied a whole-file shift instead.`,
});

describe('FixNoticePanel', () => {
  it('names the scope and repeats the tool\'s own words', () => {
    render(<FixNoticePanel notices={[notice('vocals')]} />);

    expect(screen.getByText('One fix did less than it said')).toBeInTheDocument();
    expect(screen.getByText('vocals')).toBeInTheDocument();
    expect(screen.getByText('vocals: applied a whole-file shift instead.')).toBeInTheDocument();
  });

  it('counts them when more than one fix fell short', () => {
    render(<FixNoticePanel notices={[notice('vocals'), notice('bass')]} />);

    expect(screen.getByText('2 fixes did less than they said')).toBeInTheDocument();
  });

  // The sidebar renders it on every pass, and most renders have nothing to
  // confess — so the quiet case is the common one, not the edge case.
  it('renders nothing when the render had nothing to report', () => {
    const { container } = render(<FixNoticePanel notices={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
