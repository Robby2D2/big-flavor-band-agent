import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import VersionDetails, { VersionDetail } from '@/components/produce/audio/VersionDetails';

const version: VersionDetail = {
  id: 52,
  name: 'Original',
  label: 'original',
  is_published: false,
  steps_applied: null,
  aggressiveness: null,
  duration_seconds: 144,
  file_size_bytes: 3_900_000,
  created_at: null,
};

const props = {
  version,
  canDelete: true,
  busy: false,
  onSetDefault: vi.fn(),
  onRename: vi.fn(),
  onDelete: vi.fn(),
  onStartAnalysis: vi.fn(),
  onAnalyzeAndSave: vi.fn(),
  onSeparateStems: vi.fn(),
  analyzing: false,
  analysisNote: null,
  hasStems: true,
};

describe('VersionDetails', () => {
  it('renames in place from the pencil beside the name', () => {
    const onRename = vi.fn();
    render(<VersionDetails {...props} onRename={onRename} />);

    fireEvent.click(screen.getByRole('button', { name: 'Rename version' }));
    const input = screen.getByRole('textbox', { name: 'Version name' });
    fireEvent.change(input, { target: { value: '  Live take  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onRename).toHaveBeenCalledWith('Live take');
  });

  it('does not rename when the name is unchanged or the edit is cancelled', () => {
    const onRename = vi.fn();
    render(<VersionDetails {...props} onRename={onRename} />);

    fireEvent.click(screen.getByRole('button', { name: 'Rename version' }));
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Version name' }), { key: 'Enter' });
    fireEvent.click(screen.getByRole('button', { name: 'Rename version' }));
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Version name' }), { key: 'Escape' });

    expect(onRename).not.toHaveBeenCalled();
  });

  it('makes the version the default from its checkbox, which then cannot be unticked', () => {
    const onSetDefault = vi.fn();
    const { rerender } = render(<VersionDetails {...props} onSetDefault={onSetDefault} />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Default version' }));
    expect(onSetDefault).toHaveBeenCalledTimes(1);

    rerender(<VersionDetails {...props} version={{ ...version, is_published: true }} />);
    const box = screen.getByRole('checkbox', { name: 'Default version' });
    expect(box).toBeChecked();
    expect(box).toBeDisabled();
  });

  it('keeps the last version from being deleted', () => {
    render(<VersionDetails {...props} canDelete={false} />);

    expect(screen.getByRole('button', { name: 'Delete version' })).toBeDisabled();
  });

  it('runs analysis from the button and the other two jobs from its menu', () => {
    const onStartAnalysis = vi.fn();
    const onAnalyzeAndSave = vi.fn();
    const onSeparateStems = vi.fn();
    render(
      <VersionDetails
        {...props}
        onStartAnalysis={onStartAnalysis}
        onAnalyzeAndSave={onAnalyzeAndSave}
        onSeparateStems={onSeparateStems}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^Start analysis/ }));
    expect(onStartAnalysis).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'More analysis options' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^Analyze & save/ }));
    expect(onAnalyzeAndSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'More analysis options' }));
    fireEvent.click(screen.getByRole('menuitem', { name: /^Separate stems again/ }));
    expect(onSeparateStems).toHaveBeenCalledTimes(1);
  });

  it('locks every job while a render is running', () => {
    render(<VersionDetails {...props} renderInProgress />);

    expect(screen.getByRole('button', { name: /^Start analysis/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'More analysis options' })).toBeDisabled();
    expect(screen.getByText(/actions are paused/)).toBeInTheDocument();
  });

  it('holds the player it is given', () => {
    render(
      <VersionDetails {...props}>
        <div data-testid="player" />
      </VersionDetails>
    );

    expect(screen.getByTestId('player')).toBeInTheDocument();
  });
});
