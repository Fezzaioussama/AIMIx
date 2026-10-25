import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { PipelineStep, Run, RunStep } from '../../core/api/types';
import { LiveRun } from './LiveRun';
import { makeRun, runStep } from './testData';

/** research (1) -> writer (2) -> QA (3, sends work back to 2) -> SEO (4, only for blogs). */
function definitionStep(order: number, title: string, flow: Partial<PipelineStep>): PipelineStep {
  return {
    order,
    stage: order,
    title,
    is_output: order === 2 || order === 4,
    expected_output: '',
    prompt: `${title} {input}`,
    model: 'vendor/writer',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
    ...flow,
  };
}

const DEFINITION = [
  definitionStep(1, 'Research', {}),
  definitionStep(2, 'Writer', {}),
  definitionStep(3, 'QA', { review: { send_back_to_stage: 2, max_rounds: 2 } }),
  definitionStep(4, 'SEO', {
    condition: { source: 'previous_output', operator: 'contains', value: 'blog' },
  }),
];

/** A step of that run: the shape of `runStep`, for any of the four. */
function flowStep(order: number, status: RunStep['status'], fields: Partial<RunStep> = {}) {
  const source = DEFINITION[order - 1];
  return {
    ...runStep(1, status, status === 'succeeded' ? `${source.title} text` : ''),
    step_order: order,
    stage: source.stage,
    title: source.title,
    is_output: source.is_output,
    ...fields,
  };
}

function flowRun(overrides: Partial<Run> = {}): Run {
  return makeRun({
    definition: { name: 'Post', inputs: [], steps: DEFINITION },
    ...overrides,
  });
}

const done = {
  status: 'succeeded' as const,
  finished_at: '2026-10-24T10:00:09Z',
};

describe('LiveRun: skipped steps', () => {
  const run = flowRun({
    ...done,
    steps: [
      flowStep(1, 'succeeded'),
      flowStep(2, 'succeeded'),
      flowStep(3, 'succeeded', { rounds: 1, verdict: 'pass' }),
      flowStep(4, 'skipped'),
    ],
  });

  it('counts a skipped step as done and says how many there were', () => {
    render(<LiveRun run={run} />);

    expect(screen.getByText('4 of 4 steps done (1 skipped)')).toBeInTheDocument();
    expect(screen.getByText('Run done. 4 of 4 steps done (1 skipped).')).toBeInTheDocument();
  });

  it('shows the step as skipped on the diagram', () => {
    render(<LiveRun run={run} />);

    expect(
      screen.getByRole('button', { name: /SEO, .*, Skipped, its condition was not met/ }),
    ).toBeDisabled();
  });

  it('says in the step list that its condition was not met, and what the condition was', async () => {
    render(<LiveRun run={run} />);

    await userEvent.click(screen.getByRole('tab', { name: 'All steps (4)' }));

    expect(
      screen.getByText(
        /Skipped\. Its condition was not met\. It runs only if the previous result contains “blog”\./,
      ),
    ).toBeInTheDocument();
  });

  it('does not offer a skipped step as an output, nor mark it as one', async () => {
    render(<LiveRun run={run} diagram={false} />);

    expect(screen.getByRole('tab', { name: 'Outputs (1)' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'All steps (4)' }));
    const heading = screen.getByText('SEO').parentElement as HTMLElement;
    expect(within(heading).queryByText('Output')).not.toBeInTheDocument();
    expect(within(heading).getByText('Skipped')).toBeInTheDocument();
  });

  it('explains an empty Outputs tab when the steps that make the outputs were skipped', () => {
    const none = flowRun({
      ...done,
      definition: {
        name: 'Post',
        inputs: [],
        steps: DEFINITION.map((step) => ({ ...step, is_output: step.order === 4 })),
      },
      steps: [
        flowStep(1, 'succeeded'),
        flowStep(2, 'succeeded', { is_output: false }),
        flowStep(3, 'succeeded', { is_output: false }),
        flowStep(4, 'skipped'),
      ],
    });
    render(<LiveRun run={none} />);

    expect(screen.getByRole('tab', { name: 'Outputs (0)' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'No outputs: the steps that make them were skipped because their condition was not met.',
      ),
    ).toBeInTheDocument();
  });

  it('keeps the usual words while a run could still make its outputs', () => {
    const going = flowRun({
      steps: [flowStep(1, 'succeeded'), flowStep(2, 'running'), flowStep(3, 'pending')],
    });
    render(<LiveRun run={going} />);

    expect(screen.getByText('Waiting for the steps before it.')).toBeInTheDocument();
    expect(screen.queryByText(/No outputs: the steps/)).not.toBeInTheDocument();
  });
});

describe('LiveRun: review rounds', () => {
  const rounds = (n: number, verdict: RunStep['verdict']) => ({ rounds: n, verdict });

  it('marks a step that ran again with its round, out of the most it may take', async () => {
    const run = flowRun({
      ...done,
      steps: [
        flowStep(1, 'succeeded'),
        flowStep(2, 'succeeded', rounds(2, null)),
        flowStep(3, 'succeeded', rounds(2, 'pass')),
        flowStep(4, 'skipped'),
      ],
    });
    render(<LiveRun run={run} diagram={false} />);
    await userEvent.click(screen.getByRole('tab', { name: 'All steps (4)' }));

    expect(screen.getAllByText('Round 2 of 3')).toHaveLength(2);
    expect(screen.queryByText('Round 1 of 3')).not.toBeInTheDocument();
  });

  it('shows a step that is running again as it works, with its round', () => {
    const run = flowRun({
      steps: [
        flowStep(1, 'succeeded'),
        flowStep(2, 'running', { rounds: 2 }),
        flowStep(3, 'succeeded', rounds(1, 'revise')),
      ],
    });
    render(<LiveRun run={run} diagram={false} />);

    expect(screen.getByText('Round 2 of 3')).toBeInTheDocument();
    // A reviewer that has just asked for fixes says so, while the work goes back.
    expect(screen.getByText('Asked for fixes: the work goes back for round 2')).toBeInTheDocument();
  });

  it.each([
    ['approved after being sent back', 3, 'pass', 'Sent back 2 times, then approved'],
    ['out of rounds', 3, 'revise', 'Sent back 2 times, then accepted'],
    ['one time and then approved', 2, 'pass', 'Sent back 1 time, then approved'],
    [
      'no verdict after being sent back',
      2,
      null,
      'Sent back 1 time, then moved on without a verdict',
    ],
    ['no verdict the first time', 1, null, 'It gave no verdict, so the work moved on'],
  ] as const)(
    'tells what the reviewer’s last answer led to: %s',
    async (_name, n, verdict, note) => {
      const run = flowRun({
        ...done,
        steps: [
          flowStep(1, 'succeeded'),
          flowStep(2, 'succeeded', rounds(n, null)),
          flowStep(3, 'succeeded', rounds(n, verdict)),
          flowStep(4, 'skipped'),
        ],
      });
      render(<LiveRun run={run} diagram={false} />);
      await userEvent.click(screen.getByRole('tab', { name: 'All steps (4)' }));

      expect(screen.getByText(note)).toBeInTheDocument();
    },
  );

  it('says nothing about a reviewer that approved the first time', async () => {
    const run = flowRun({
      ...done,
      steps: [
        flowStep(1, 'succeeded'),
        flowStep(2, 'succeeded'),
        flowStep(3, 'succeeded', rounds(1, 'pass')),
        flowStep(4, 'skipped'),
      ],
    });
    render(<LiveRun run={run} diagram={false} />);
    await userEvent.click(screen.getByRole('tab', { name: 'All steps (4)' }));

    expect(screen.queryByText(/Sent back|moved on|Asked for fixes/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Round \d/)).not.toBeInTheDocument();
  });

  it('shows no reviewer note while the reviewer is working again', () => {
    const run = flowRun({
      steps: [
        flowStep(1, 'succeeded'),
        flowStep(2, 'succeeded', rounds(2, null)),
        flowStep(3, 'running', rounds(2, null)),
      ],
    });
    render(<LiveRun run={run} diagram={false} />);

    expect(screen.queryByText(/Sent back|Asked for fixes/)).not.toBeInTheDocument();
    expect(screen.getAllByText('Round 2 of 3')).toHaveLength(2);
  });
});
