import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { LiveRun } from './LiveRun';
import { makeRun, runStep } from './testData';

describe('LiveRun', () => {
  it('shows each step live on the diagram, with Stop while the run is active', async () => {
    const onStop = vi.fn();
    render(<LiveRun run={makeRun()} onStop={onStop} onResume={vi.fn()} />);

    expect(
      screen.getByRole('button', { name: /Research, writer, intermediate, Done/ }),
    ).toBeEnabled();
    expect(screen.getByRole('button', { name: /Draft, writer, output, Running/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Summary, writer, output, Waiting/ })).toBeDisabled();
    expect(screen.getByText('1 of 3 steps done')).toBeInTheDocument();
    expect(screen.getByText('Run running. 1 of 3 steps done.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it('opens on the progress of a run in flight, with saved outputs already readable', () => {
    render(<LiveRun run={makeRun()} />);

    expect(screen.getByRole('tab', { name: 'All steps (3)' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByText('Research notes')).toBeInTheDocument();
    expect(screen.getByText('Working on it…')).toBeInTheDocument();
    expect(screen.getByText('Waiting for the steps before it.')).toBeInTheDocument();
  });

  it('explains a failure, keeps finished work, and offers Resume', async () => {
    const onResume = vi.fn();
    const failed = makeRun({
      status: 'failed',
      finished_at: '2026-10-24T10:00:05Z',
      error: { code: 'provider_timeout', detail: 'The agent timed out.' },
      steps: [
        runStep(1, 'succeeded', 'Research notes'),
        runStep(2, 'failed'),
        runStep(3, 'cancelled'),
      ],
    });
    render(<LiveRun run={failed} onStop={vi.fn()} onResume={onResume} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Draft failed. The agent timed out.');
    expect(screen.getByRole('button', { name: /Draft, writer, output, Failed/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Summary, writer, output, Stopped/ })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(onResume).toHaveBeenCalledOnce();
  });

  it('opens a finished run on its outputs, with its tool use', async () => {
    const done = makeRun({
      status: 'succeeded',
      finished_at: '2026-10-24T10:00:09Z',
      steps: [
        runStep(1, 'succeeded', 'Research notes'),
        runStep(2, 'succeeded', 'Draft text'),
        runStep(3, 'succeeded', 'Summary text'),
      ],
    });
    render(<LiveRun run={done} onStop={vi.fn()} onResume={vi.fn()} />);

    expect(screen.getByRole('tab', { name: 'Outputs (2)' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByText('Draft text')).toBeInTheDocument();
    expect(screen.queryByText('Research notes')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop|Resume/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'All steps (3)' }));
    expect(screen.getAllByText('Tools used (1)')).toHaveLength(3);
  });

  it('says why an interrupted run stopped', () => {
    render(<LiveRun run={makeRun({ status: 'interrupted' })} onResume={vi.fn()} />);

    expect(
      screen.getByText('The server restarted while this run was in progress.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeEnabled();
  });
});
