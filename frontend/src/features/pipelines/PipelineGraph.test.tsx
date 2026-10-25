import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type {
  PipelineInput,
  PipelineStep,
  RunStep,
  StepCondition,
  StepReview,
} from '../../core/api/types';
import { PipelineGraph } from './PipelineGraph';

function step(order: number, stage: number, title: string, flow: Partial<PipelineStep> = {}) {
  const base: PipelineStep = {
    order,
    stage,
    title,
    is_output: false,
    expected_output: '',
    prompt: `${title} prompt`,
    model: 'vendor/writer',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  };
  return { ...base, ...flow };
}

const BLOG: StepCondition = { source: 'previous_output', operator: 'contains', value: 'blog' };
const LOOP: StepReview = { send_back_to_stage: 2, max_rounds: 2 };
const TOPIC: PipelineInput = { name: 'topic', label: 'Topic', description: '' };

const flow = [
  step(1, 1, 'Research'),
  step(2, 2, 'Writer'),
  step(3, 3, 'QA', { review: LOOP }),
  step(4, 4, 'SEO', { condition: BLOG, is_output: true }),
];

function liveStep(order: number, status: RunStep['status'], rounds = 1): RunStep {
  const source = flow[order - 1];
  return {
    step_order: order,
    stage: source.stage,
    title: source.title,
    model: source.model,
    input_used: '',
    output: status === 'succeeded' ? 'text' : '',
    is_output: source.is_output,
    tool_calls: [],
    status,
    error: null,
    started_at: null,
    finished_at: null,
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: null,
    rounds,
    verdict: null,
  };
}

const node = (name: RegExp) => screen.getByRole('button', { name });

describe('PipelineGraph: conditions', () => {
  it('marks a step that runs only if something holds', () => {
    render(<PipelineGraph steps={flow} />);

    const seo = node(/^SEO,/);
    expect(within(seo).getByText('Only if…')).toBeInTheDocument();
    expect(seo).toHaveAccessibleName(/runs only if the previous result contains “blog”/);
  });

  it('says on hover what the condition is, before the step’s prompt', () => {
    render(<PipelineGraph steps={flow} />);

    expect(node(/^SEO,/)).toHaveAttribute(
      'title',
      'Runs only if the previous result contains “blog”\n\nSEO prompt',
    );
    expect(node(/^Research,/)).toHaveAttribute('title', 'Research prompt');
  });

  it('names an input by its label in a condition', () => {
    const looking = { source: 'input:topic', operator: 'not_empty' as const, value: '' };
    render(
      <PipelineGraph
        steps={[step(1, 1, 'Research'), step(2, 2, 'Draft', { condition: looking })]}
        inputs={[TOPIC]}
      />,
    );

    expect(node(/^Draft,/)).toHaveAccessibleName(/runs only if the input “Topic” is not empty/);
  });

  it('explains the mark in the legend only when a step has one', () => {
    const { rerender } = render(<PipelineGraph steps={[step(1, 1, 'A'), step(2, 2, 'B')]} />);
    expect(screen.queryByText('runs only if its condition holds')).not.toBeInTheDocument();

    rerender(<PipelineGraph steps={flow} />);
    expect(screen.getByText('runs only if its condition holds')).toBeInTheDocument();
  });
});

describe('PipelineGraph: review loops', () => {
  it('marks a reviewer, and says in its name where it sends the work', () => {
    render(<PipelineGraph steps={flow} />);

    const reviewer = node(/^QA,/);
    expect(within(reviewer).getByText('Reviewer')).toBeInTheDocument();
    expect(reviewer).toHaveAccessibleName(/sends the work back to stage 2, up to 2 times/);
  });

  it('draws the way back to the stage it goes to, with how many times', () => {
    render(<PipelineGraph steps={flow} />);

    expect(screen.getByText('Back here up to 2 times')).toBeInTheDocument();
  });

  it('keeps the drawing out of the way of assistive technology', () => {
    render(<PipelineGraph steps={flow} />);

    expect(
      screen.getByText('Back here up to 2 times').closest('[aria-hidden="true"]'),
    ).not.toBeNull();
  });

  it('draws nothing for a pipeline without a loop', () => {
    render(<PipelineGraph steps={[flow[0], flow[1]]} />);

    expect(screen.queryByText(/Back here up to/)).not.toBeInTheDocument();
    expect(screen.queryByText('can send the work back (the purple line)')).not.toBeInTheDocument();
  });

  it('draws nothing for a loop that cannot work', () => {
    const broken = [
      step(1, 1, 'A'),
      step(2, 2, 'B', { review: { send_back_to_stage: 5, max_rounds: 1 } }),
    ];
    render(<PipelineGraph steps={broken} />);

    expect(screen.queryByText(/Back here up to/)).not.toBeInTheDocument();
  });

  it('says "1 time" for a single round', () => {
    const once = [
      step(1, 1, 'A'),
      step(2, 2, 'B', { review: { send_back_to_stage: 1, max_rounds: 1 } }),
    ];
    render(<PipelineGraph steps={once} />);

    expect(screen.getByText('Back here up to 1 time')).toBeInTheDocument();
  });

  it('draws a line for each loop', () => {
    const two = [
      step(1, 1, 'A'),
      step(2, 2, 'B', { review: { send_back_to_stage: 1, max_rounds: 1 } }),
      step(3, 3, 'C'),
      step(4, 4, 'D', { review: { send_back_to_stage: 3, max_rounds: 3 } }),
    ];
    render(<PipelineGraph steps={two} />);

    expect(screen.getByText('Back here up to 1 time')).toBeInTheDocument();
    expect(screen.getByText('Back here up to 3 times')).toBeInTheDocument();
  });

  it('explains the mark in the legend', () => {
    render(<PipelineGraph steps={flow} />);

    expect(screen.getByText('can send the work back (the purple line)')).toBeInTheDocument();
  });
});

describe('PipelineGraph: a followed run', () => {
  it('shows a skipped step as skipped, says why, and drops its output mark', () => {
    const steps = [liveStep(1, 'succeeded'), liveStep(4, 'skipped')];
    render(<PipelineGraph steps={flow} liveSteps={steps} />);

    const seo = node(/^SEO,/);
    expect(seo).toHaveAccessibleName(/intermediate, Skipped, its condition was not met/);
    expect(seo).toHaveAttribute(
      'title',
      'Its condition was not met: it runs only if the previous result contains “blog”',
    );
    expect(within(seo).queryByText('Output')).not.toBeInTheDocument();
  });

  it('shows the round a step that ran again is in, out of the most it may take', () => {
    const steps = [liveStep(1, 'succeeded'), liveStep(2, 'running', 2), liveStep(3, 'succeeded')];
    render(<PipelineGraph steps={flow} liveSteps={steps} isRunning />);

    const writer = node(/^Writer,/);
    expect(within(writer).getByText('Round 2 of 3')).toBeInTheDocument();
    expect(writer).toHaveAccessibleName(/Running, round 2 of 3/);
    // A step that ran once shows no round.
    expect(within(node(/^Research,/)).queryByText(/Round/)).not.toBeInTheDocument();
  });

  it('shows no round for the first time through', () => {
    render(<PipelineGraph steps={flow} liveSteps={[liveStep(2, 'running')]} isRunning />);

    expect(within(node(/^Writer,/)).queryByText(/Round/)).not.toBeInTheDocument();
  });
});
