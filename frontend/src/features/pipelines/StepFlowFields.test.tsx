import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { PipelineInput, PipelineStep } from '../../core/api/types';
import { StepFlowFields } from './StepFlowFields';

function step(order: number, stage: number, title: string, flow: Partial<PipelineStep> = {}) {
  const base: PipelineStep = {
    order,
    stage,
    title,
    is_output: false,
    expected_output: '',
    prompt: 'p',
    model: 'v/m',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  };
  return { ...base, ...flow };
}

const TOPIC: PipelineInput = { name: 'topic', label: 'Topic', description: '' };

interface HarnessProps {
  steps: PipelineStep[];
  editing: number;
  inputs?: PipelineInput[];
}

/** Edits step `editing` of `steps`, and prints the flow fields it holds. */
function Harness({ steps: initial, editing, inputs = [] }: HarnessProps) {
  const [steps, setSteps] = useState(initial);
  const current = steps.find((item) => item.order === editing) as PipelineStep;
  return (
    <>
      <StepFlowFields
        step={current}
        steps={steps}
        inputs={inputs}
        onChange={(patch) =>
          setSteps((all) =>
            all.map((item) => (item.order === editing ? { ...item, ...patch } : item)),
          )
        }
      />
      <output data-testid="flow">
        {JSON.stringify({ condition: current.condition, review: current.review })}
      </output>
    </>
  );
}

const flowOf = () => JSON.parse(screen.getByTestId('flow').textContent ?? '{}');

const team = [step(1, 1, 'Research'), step(2, 2, 'Writer'), step(3, 3, 'Reviewer')];

describe('StepFlowFields: the condition', () => {
  it('starts folded away and says the step always runs', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={2} />);

    const section = screen.getByText('Run this step only if…').closest('details');
    expect(section).not.toHaveAttribute('open');

    await user.click(screen.getByText('Run this step only if…'));
    expect(section).toHaveAttribute('open');
    expect(within(section as HTMLElement).getByText('This step always runs.')).toBeVisible();
  });

  it('adds a condition that looks at the previous result and asks for text', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={2} />);
    await user.click(screen.getByText('Run this step only if…'));

    await user.click(screen.getByRole('button', { name: 'Add a condition' }));

    expect(flowOf().condition).toEqual({
      source: 'previous_output',
      operator: 'contains',
      value: '',
    });
    expect(screen.getByLabelText('What to look at')).toHaveValue('previous_output');
    expect(screen.getByLabelText('Check whether it')).toHaveValue('contains');
    expect(screen.getByText('Enter the text to compare with.')).toBeInTheDocument();
    expect(screen.getByLabelText('Text to compare with')).toHaveAttribute('maxlength', '200');
  });

  it('offers the previous result, each input and the steps of earlier stages by name', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={3} inputs={[TOPIC]} />);
    await user.click(screen.getByText('Run this step only if…'));
    await user.click(screen.getByRole('button', { name: 'Add a condition' }));

    const options = within(screen.getByLabelText('What to look at'))
      .getAllByRole('option')
      .map((option) => option.textContent);

    expect(options).toEqual([
      'The previous stage’s result',
      'Input: Topic',
      'Result of “Research” (step 1)',
      'Result of “Writer” (step 2)',
    ]);
  });

  it('changes what it looks at, how, and with what text', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={3} inputs={[TOPIC]} />);
    await user.click(screen.getByText('Run this step only if…'));
    await user.click(screen.getByRole('button', { name: 'Add a condition' }));

    await user.selectOptions(screen.getByLabelText('What to look at'), 'input:topic');
    await user.selectOptions(screen.getByLabelText('Check whether it'), 'not_contains');
    await user.type(screen.getByLabelText('Text to compare with'), 'blog');

    expect(flowOf().condition).toEqual({
      source: 'input:topic',
      operator: 'not_contains',
      value: 'blog',
    });
    expect(screen.queryByText('Enter the text to compare with.')).not.toBeInTheDocument();
  });

  it('shows what is set in a few words next to the title, while folded', () => {
    render(
      <Harness
        steps={[
          team[0],
          step(2, 2, 'Writer', {
            condition: { source: 'step:1', operator: 'contains', value: 'blog' },
          }),
        ]}
        editing={2}
      />,
    );

    expect(screen.getByText(/the result of “Research” \(step 1\) contains “blog”/)).toBeVisible();
  });

  it('hides the text, and forgets it, for a comparison that takes none', async () => {
    const user = userEvent.setup();
    render(
      <Harness
        steps={[
          team[0],
          step(2, 2, 'Writer', {
            condition: { source: 'previous_output', operator: 'contains', value: 'blog' },
          }),
        ]}
        editing={2}
      />,
    );
    await user.click(screen.getByText('Run this step only if…'));

    await user.selectOptions(screen.getByLabelText('Check whether it'), 'is_empty');

    expect(screen.queryByLabelText('Text to compare with')).not.toBeInTheDocument();
    expect(flowOf().condition).toEqual({
      source: 'previous_output',
      operator: 'is_empty',
      value: '',
    });
    // Back to a comparison with text: the box is back, empty.
    await user.selectOptions(screen.getByLabelText('Check whether it'), 'equals');
    expect(screen.getByLabelText('Text to compare with')).toHaveValue('');
  });

  it('removes the condition', async () => {
    const user = userEvent.setup();
    const condition = { source: 'step:1', operator: 'not_empty' as const, value: '' };
    render(<Harness steps={[team[0], step(2, 2, 'Writer', { condition })]} editing={2} />);
    await user.click(screen.getByText('Run this step only if…'));

    await user.click(screen.getByRole('button', { name: 'Remove the condition' }));

    expect(flowOf().condition).toBeNull();
    expect(screen.getByText('This step always runs.')).toBeInTheDocument();
  });

  it('keeps a source that is no longer on offer in the list, and says what is wrong', async () => {
    const user = userEvent.setup();
    const condition = { source: 'step:0', operator: 'not_empty' as const, value: '' };
    render(<Harness steps={[team[0], step(2, 2, 'Writer', { condition })]} editing={2} />);
    await user.click(screen.getByText('Run this step only if…'));

    const select = screen.getByLabelText('What to look at');
    expect(select).toHaveValue('step:0');
    expect(within(select).getByRole('option', { name: 'Not available any more' })).toBeVisible();
    expect(select).toHaveAttribute('aria-invalid', 'true');
    expect(
      screen.getByText('The step this condition looked at was removed. Choose again.'),
    ).toBeInTheDocument();
  });

  it('says in words that capital letters and spaces do not matter, and what happens', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={2} />);
    await user.click(screen.getByText('Run this step only if…'));
    await user.click(screen.getByRole('button', { name: 'Add a condition' }));

    expect(
      screen.getByText(/Capital letters and spaces around the text do not matter/),
    ).toBeVisible();
    expect(screen.getByText(/“Writer” is skipped/)).toBeInTheDocument();
  });
});

describe('StepFlowFields: the review loop', () => {
  it('is not offered to a step with no earlier stage', () => {
    render(<Harness steps={team} editing={1} />);

    expect(screen.getByText('Run this step only if…')).toBeInTheDocument();
    expect(screen.queryByText('Review loop')).not.toBeInTheDocument();
  });

  it('is offered from the second stage on, folded away', () => {
    render(<Harness steps={team} editing={2} />);

    expect(screen.getByText('Review loop').closest('details')).not.toHaveAttribute('open');
  });

  it('makes a step a reviewer that sends the work back to the stage before, twice at most', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={3} />);
    await user.click(screen.getByText('Review loop'));
    expect(screen.getByText('This step does not send work back.')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Make this step a reviewer' }));

    expect(flowOf().review).toEqual({ send_back_to_stage: 2, max_rounds: 2 });
    expect(screen.getByLabelText('Send the work back to stage')).toHaveValue('2');
    expect(screen.getByLabelText('Most times to send the work back')).toHaveValue('2');
    expect(screen.getByText(/when this step says the work needs fixes/)).toBeVisible();
  });

  it('tells the person the prompt should judge the work', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={3} />);
    await user.click(screen.getByText('Review loop'));
    await user.click(screen.getByRole('button', { name: 'Make this step a reviewer' }));

    expect(screen.getByText(/judges the work it receives and says what to fix/)).toBeVisible();
  });

  it('lists the earlier stages with the names of their steps, and one to five times', async () => {
    const user = userEvent.setup();
    const steps = [team[0], step(2, 2, 'Draft'), step(3, 2, 'Outline'), step(4, 3, 'Reviewer')];
    render(<Harness steps={steps} editing={4} />);
    await user.click(screen.getByText('Review loop'));
    await user.click(screen.getByRole('button', { name: 'Make this step a reviewer' }));

    const stages = within(screen.getByLabelText('Send the work back to stage')).getAllByRole(
      'option',
    );
    const times = within(screen.getByLabelText('Most times to send the work back')).getAllByRole(
      'option',
    );

    expect(stages.map((option) => option.textContent)).toEqual([
      '1 · Research',
      '2 · Draft, Outline',
    ]);
    expect(times.map((option) => option.textContent)).toEqual([
      '1 time',
      '2 times',
      '3 times',
      '4 times',
      '5 times',
    ]);
  });

  it('changes where the work goes and how many times', async () => {
    const user = userEvent.setup();
    render(<Harness steps={team} editing={3} />);
    await user.click(screen.getByText('Review loop'));
    await user.click(screen.getByRole('button', { name: 'Make this step a reviewer' }));

    await user.selectOptions(screen.getByLabelText('Send the work back to stage'), '1');
    await user.selectOptions(screen.getByLabelText('Most times to send the work back'), '4');

    expect(flowOf().review).toEqual({ send_back_to_stage: 1, max_rounds: 4 });
    expect(screen.getByText(/Sends the work back to stage 1, up to 4 times/)).toBeVisible();
  });

  it('removes the review loop', async () => {
    const user = userEvent.setup();
    const review = { send_back_to_stage: 1, max_rounds: 1 };
    render(<Harness steps={[team[0], team[1], step(3, 3, 'Reviewer', { review })]} editing={3} />);
    await user.click(screen.getByText('Review loop'));

    await user.click(screen.getByRole('button', { name: 'Remove the review loop' }));

    expect(flowOf().review).toBeNull();
    expect(screen.getByRole('button', { name: 'Make this step a reviewer' })).toBeVisible();
  });

  it('says what is wrong with a loop that cannot work, and keeps the stage it points at', async () => {
    const user = userEvent.setup();
    const review = { send_back_to_stage: 7, max_rounds: 1 };
    render(<Harness steps={[team[0], team[1], step(3, 3, 'Reviewer', { review })]} editing={3} />);
    await user.click(screen.getByText('Review loop'));

    const stage = screen.getByLabelText('Send the work back to stage');
    expect(stage).toHaveValue('7');
    expect(stage).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/Stage 7 is not an earlier stage with steps/)).toBeInTheDocument();
  });

  it('stays available to a step that has a review but no earlier stage, so it can be removed', async () => {
    const user = userEvent.setup();
    const review = { send_back_to_stage: 1, max_rounds: 1 };
    render(<Harness steps={[step(1, 1, 'Only', { review })]} editing={1} />);

    await user.click(screen.getByText('Review loop'));

    expect(screen.getByRole('button', { name: 'Remove the review loop' })).toBeVisible();
  });
});
