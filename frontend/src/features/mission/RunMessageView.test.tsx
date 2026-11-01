import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { Run } from '../../core/api/types';
import { makeRun } from '../runs/testData';
import type { MessageContext } from './messageContext';
import { RunMessageView } from './RunMessageView';

/** The view as the conversation draws it: inside its polite log, `run` the newest run. */
function renderInLog(run: Run) {
  // Only what the run's bubble reads from the workspace.
  const context = { latestRun: run, showPane: vi.fn() } as unknown as MessageContext;
  const view = (shown: Run) => (
    <MemoryRouter>
      <div role="log" aria-live="polite">
        <RunMessageView
          message={{ id: 'run-1', from: 'aimix', kind: 'run', runId: shown.id }}
          context={{ ...context, latestRun: shown }}
        />
      </div>
    </MemoryRouter>
  );
  const rendered = render(view(run));
  return { poll: (next: Run) => rendered.rerender(view(next)) };
}

describe('RunMessageView', () => {
  it('keeps its run line in step without speaking it: the run report announces the run', () => {
    const { poll } = renderInLog(makeRun({ status: 'running' }));

    poll(makeRun({ status: 'cancelled' }));

    const line = screen.getByText('You stopped this run. You can resume it under Results.');
    // The log speaks what is added to it; this line changes in place, which the report's
    // announcer already says ("You stopped the run."), so it must not be heard twice.
    expect(line.closest('[aria-live]')).toHaveAttribute('aria-live', 'off');
    expect(screen.getByRole('button', { name: 'See results' })).toBeInTheDocument();
  });
});
