import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Pipeline, PipelineStep } from '../../core/api/types';
import { GeneratedSteps } from './GeneratedSteps';

function step(order: number, stage: number, title: string, flow: Partial<PipelineStep> = {}) {
  const base: PipelineStep = {
    order,
    stage,
    title,
    is_output: false,
    expected_output: '',
    prompt: `${title} {input}`,
    model: 'vendor/fast',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  };
  return { ...base, ...flow };
}

/** A plan the planner wrote: a writer, and a QA step that sends its work back. */
const plan: Pipeline = {
  name: 'Posts',
  inputs: [],
  steps: [
    step(1, 1, 'Writer'),
    step(2, 2, 'QA', { review: { send_back_to_stage: 1, max_rounds: 2 } }),
    step(3, 3, 'SEO', {
      condition: { source: 'step:1', operator: 'contains', value: 'blog' },
    }),
  ],
};

function renderPlan(onChange = vi.fn()) {
  render(
    <GeneratedSteps
      pipeline={plan}
      availableModels={['vendor/fast']}
      availableTools={[]}
      onChange={onChange}
      onRemove={vi.fn()}
    />,
  );
  return onChange;
}

describe('GeneratedSteps: what the planner decided about the flow', () => {
  it('shows a review loop the planner wrote, in words, on the step that has it', () => {
    renderPlan();

    expect(screen.getByText(/Sends the work back to stage 1, up to 2 times/)).toBeInTheDocument();
  });

  it('shows a condition the planner wrote, in words, on the step that has it', () => {
    renderPlan();

    expect(
      screen.getByText(/the result of “Writer” \(step 1\) contains “blog”/),
    ).toBeInTheDocument();
  });

  it('lets the person change it before saving', async () => {
    const user = userEvent.setup();
    const onChange = renderPlan();
    // QA is the first step with a review section: the writer has no earlier stage.
    await user.click(screen.getAllByText('Review loop')[0]);

    await user.selectOptions(screen.getByLabelText('Most times to send the work back'), '4');

    expect(onChange).toHaveBeenCalledWith(1, { review: { send_back_to_stage: 1, max_rounds: 4 } });
  });

  it('offers a review loop to a step with an earlier stage, and not to the first', () => {
    renderPlan();

    // QA and SEO have earlier stages; the writer, in the first, has none.
    expect(screen.getAllByText('Review loop')).toHaveLength(2);
    expect(screen.getAllByText('Run this step only if…')).toHaveLength(3);
    const writer = screen
      .getByText('Writer', { selector: 'span.font-semibold' })
      .closest('div.rounded-xl');
    expect(within(writer as HTMLElement).queryByText('Review loop')).not.toBeInTheDocument();
  });
});
