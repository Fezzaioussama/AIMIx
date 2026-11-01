import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Pipeline } from '../../core/api/types';
import { PlannedDeliverables } from './PlannedDeliverables';
import { PLAN, planStep } from './testData';

/** PLAN with a final check in its own stage, as the planner adds one. */
function withCheck(isOutput: boolean): Pipeline {
  const check = {
    ...planStep(3, 3, 'Final check', isOutput),
    role: 'Orchestrator',
    review: { send_back_to_stage: 2, max_rounds: 2 },
  };
  return { ...PLAN, steps: [...PLAN.steps, check] };
}

const region = () => within(screen.getByRole('region', { name: 'Deliverables' }));

describe('PlannedDeliverables', () => {
  it('names each deliverable as its document will be, what it holds and who makes it', () => {
    render(<PlannedDeliverables team={PLAN} />);

    expect(region().getByText('When your team has run, you get this:')).toBeInTheDocument();
    const items = region().getAllByRole('listitem');
    expect(items).toHaveLength(1);
    expect(within(items[0]).getByText('Comparison')).toBeInTheDocument();
    expect(within(items[0]).getByText('Comparison result')).toBeInTheDocument();
    expect(within(items[0]).getByText('by Analyst')).toBeInTheDocument();
    // The research only feeds the comparison: it is not handed over.
    expect(region().queryByText('Market research')).not.toBeInTheDocument();
  });

  it('says “these” for several deliverables', () => {
    const team = { ...PLAN, steps: PLAN.steps.map((step) => ({ ...step, is_output: true })) };
    render(<PlannedDeliverables team={team} />);

    expect(region().getByText('When your team has run, you get these:')).toBeInTheDocument();
    expect(region().getAllByRole('listitem')).toHaveLength(2);
  });

  it('says who checks the work, and leaves the check out of the deliverables', () => {
    render(<PlannedDeliverables team={withCheck(true)} />);

    expect(
      region().getByText('The Orchestrator checks the work before it reaches you.'),
    ).toBeInTheDocument();
    expect(region().getAllByRole('listitem')).toHaveLength(1);
    expect(region().queryByText('Final check')).not.toBeInTheDocument();
  });

  it('keeps a check that is the only output as the deliverable, with nothing checking it', () => {
    const team = { ...withCheck(true), steps: withCheck(true).steps.slice(2) };
    render(<PlannedDeliverables team={team} />);

    expect(region().getByText('Final check')).toBeInTheDocument();
    expect(region().queryByText(/checks the work/)).not.toBeInTheDocument();
  });

  it('names a step without a title by its place, and leaves out what it does not say', () => {
    const bare = { ...planStep(2, 2, '', true), expected_output: ' ', role: '' };
    render(<PlannedDeliverables team={{ ...PLAN, steps: [PLAN.steps[0], bare] }} />);

    const item = within(region().getByRole('listitem'));
    expect(item.getByText('Step 2')).toBeInTheDocument();
    expect(item.queryByText(/^by /)).not.toBeInTheDocument();
    expect(item.getAllByText(/./)).toHaveLength(1);
  });

  it('says where results will appear before there is a team', () => {
    render(<PlannedDeliverables team={null} />);

    expect(
      screen.getByText('Your results appear here once your team has worked on a mission.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });
});
