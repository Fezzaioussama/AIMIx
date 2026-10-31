import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { RunStep } from '../../core/api/types';
import { makeRun, runStep } from '../runs/testData';
import { Deliverables } from './Deliverables';

/** Step 1 is intermediate work; steps 2 and 3 are deliverables. */
function showRun(steps: RunStep[]) {
  render(<Deliverables run={makeRun({ status: 'succeeded', steps })} team={null} />);
}

function agentsWork() {
  return screen.queryByRole('region', { name: 'What each other agent did' });
}

describe('Deliverables', () => {
  it('shows the work of every agent, the deliverables first', () => {
    showRun([
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'succeeded', 'The draft'),
      runStep(3, 'succeeded', 'The summary'),
    ]);

    const deliverables = screen.getByRole('region', { name: 'Deliverables' });
    const others = agentsWork();
    expect(within(deliverables).getByText('The draft')).toBeInTheDocument();
    expect(others).not.toBeNull();
    expect(within(others as HTMLElement).getByText('Research notes')).toBeInTheDocument();
    expect(within(others as HTMLElement).queryByText('The draft')).not.toBeInTheDocument();
  });

  it('leaves out an agent that has nothing to show yet', () => {
    showRun([
      runStep(1, 'failed'),
      runStep(2, 'succeeded', 'The draft'),
      runStep(3, 'succeeded', 'The summary'),
    ]);

    expect(agentsWork()).toBeNull();
  });
});
