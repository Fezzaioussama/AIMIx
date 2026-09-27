import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { PipelineRunView } from './PipelineRunView';

const steps: PipelineStep[] = [
  { order: 1, stage: 1, prompt: 'tweet {input}', model: 'v/writer' },
  { order: 2, stage: 1, prompt: 'email {input}', model: 'v/writer' },
  { order: 3, stage: 2, prompt: 'pick {input}', model: 'v/judge' },
];

const results: StepResult[] = [
  { step_order: 1, stage: 1, model: 'v/writer', input_used: 'bottle', output: 'Tweet text' },
  { step_order: 2, stage: 1, model: 'v/writer', input_used: 'bottle', output: 'Email text' },
  { step_order: 3, stage: 2, model: 'v/judge', input_used: 'both', output: 'The winner' },
];

function renderView(overrides: Partial<Parameters<typeof PipelineRunView>[0]> = {}) {
  return render(
    <PipelineRunView
      steps={steps}
      results={results}
      finalOutput="The winner"
      isRunning={false}
      input="bottle"
      elapsedMs={2500}
      {...overrides}
    />,
  );
}

describe('PipelineRunView', () => {
  it('draws the stages and opens on the final output with run stats', () => {
    renderView();
    expect(screen.getByText('Stage 1 · parallel')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Final output' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByText('3 steps · 2 stages · 2.5 s')).toBeInTheDocument();
  });

  it('opens a step output when its diagram node is clicked', async () => {
    renderView();
    await userEvent.click(screen.getByRole('button', { name: /Step 2, writer, Done/ }));
    expect(screen.getByRole('tab', { name: /All steps/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Email text')).toBeInTheDocument();
  });

  it('keeps unrun nodes inert and hides outputs before a run', () => {
    renderView({ results: [], finalOutput: '', elapsedMs: null });
    expect(screen.getByRole('button', { name: /Step 1, writer, Not run/ })).toBeDisabled();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('switches an output between rendered Markdown and raw text', async () => {
    renderView({ finalOutput: '**bold**' });
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    await userEvent.click(screen.getByRole('button', { name: 'Raw' }));
    expect(screen.getByText('**bold**')).toBeInTheDocument();
  });
});
