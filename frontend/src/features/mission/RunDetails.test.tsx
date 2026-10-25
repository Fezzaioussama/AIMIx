import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { Run } from '../../core/api/types';
import type { FollowedRun } from '../runs/useFollowedRun';
import { RunDetails } from './RunDetails';
import { finishedRun, runningRun } from './testData';

function followedRun(overrides: Partial<FollowedRun> = {}): FollowedRun {
  return {
    run: null,
    error: '',
    busy: false,
    stop: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    adopt: vi.fn(),
    follow: vi.fn(),
    active: false,
    shown: null,
    shownActive: false,
    shownElapsedMs: null,
    ...overrides,
  };
}

function view(run: Run, followed = followedRun()) {
  return (
    <MemoryRouter>
      <RunDetails run={run} followed={followed} />
    </MemoryRouter>
  );
}

const disclosure = () => screen.getByText('Run details').closest('details') as HTMLDetailsElement;

describe('RunDetails', () => {
  it('is open while the run works and for a run that stopped short', () => {
    const { rerender } = render(view(runningRun()));
    expect(disclosure().open).toBe(true);

    rerender(view(finishedRun({ status: 'failed', error: { code: 'x', detail: 'It broke.' } })));
    expect(disclosure().open).toBe(true);
  });

  it('is folded for a finished run, so the deliverables lead', () => {
    render(view(finishedRun()));

    expect(disclosure().open).toBe(false);
  });

  it('folds by itself when the run is done, and opens again when it is resumed', () => {
    const { rerender } = render(view(runningRun()));

    rerender(view(finishedRun()));
    expect(disclosure().open).toBe(false);

    rerender(view(runningRun()));
    expect(disclosure().open).toBe(true);
  });

  it('keeps the person’s choice while the run stays as it is', async () => {
    const { rerender } = render(view(finishedRun()));

    await userEvent.click(screen.getByText('Run details'));
    rerender(view(finishedRun({ final_output: 'changed' })));

    expect(disclosure().open).toBe(true);
  });

  it('holds the live run, with Stop and a way into the Runs screen', async () => {
    const followed = followedRun();
    render(view(runningRun(), followed));

    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));

    expect(followed.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Open in Runs' })).toHaveAttribute('href', '/runs/9');
  });
});
