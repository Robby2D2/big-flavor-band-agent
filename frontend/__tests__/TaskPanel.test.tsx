import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TaskPanel from '@/components/produce/audio/TaskPanel';
import type { Task } from '@/lib/processingTasks';

const render_: Task = {
  id: 'render',
  title: 'Rendering fixes',
  detail: 'drums: reduce noise · 3 stems left',
  state: 'running',
  done: 9,
  total: 21,
  cancelLabel: 'Cancel',
};
const analysis: Task = {
  id: 'analyze',
  title: 'Measuring the stems',
  detail: '1 of 3 parts measured',
  state: 'running',
  done: 5,
  total: 12,
  rows: [{ label: 'vocals', done: 2, total: 5 }],
  cancelLabel: 'Cancel',
};

const handlers = () => ({ onCancel: vi.fn(), onRetry: vi.fn(), onDismiss: vi.fn() });

describe('TaskPanel', () => {
  it('renders nothing when there is no work', () => {
    const { container } = render(<TaskPanel tasks={[]} {...handlers()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('counts each running task and says what it is doing', () => {
    render(<TaskPanel tasks={[render_]} {...handlers()} />);

    expect(screen.getByText('Rendering fixes')).toBeInTheDocument();
    expect(screen.getByText('9/21')).toBeInTheDocument();
    expect(screen.getByText('drums: reduce noise · 3 stems left')).toBeInTheDocument();
  });

  it('cancels one task, or all of them', async () => {
    const h = handlers();
    render(<TaskPanel tasks={[analysis, render_]} {...h} />);

    await userEvent.click(screen.getAllByRole('button', { name: 'Cancel' })[1]);
    expect(h.onCancel).toHaveBeenCalledWith('render');

    await userEvent.click(screen.getByRole('button', { name: 'Cancel all' }));
    expect(h.onCancel).toHaveBeenCalledWith('analyze');
  });

  it('offers no cancel for a task that cannot stop now', () => {
    render(
      <TaskPanel
        tasks={[{ ...render_, detail: 'Writing the new version', cancelLabel: null }]}
        {...handlers()}
      />
    );
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull();
  });

  it('offers Retry on a cancelled task and Clear once nothing runs', async () => {
    const h = handlers();
    render(<TaskPanel tasks={[{ ...analysis, state: 'cancelled', title: 'Analysis cancelled' }]} {...h} />);

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(h.onRetry).toHaveBeenCalledWith('analyze');
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(h.onDismiss).toHaveBeenCalled();
  });

  it('collapses to one line that keeps counting', async () => {
    render(<TaskPanel tasks={[render_]} {...handlers()} />);

    await userEvent.click(screen.getByRole('button', { name: 'Collapse tasks' }));

    expect(screen.getByRole('button', { name: 'Show tasks' })).toHaveTextContent(
      'Rendering fixes · 9/21'
    );
  });
});
