import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { vi } from 'vitest';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { PipelineRunView } from './PipelineRunView';

function step(order: number, stage: number, title: string, isOutput: boolean): PipelineStep {
  return {
    order,
    stage,
    title,
    is_output: isOutput,
    prompt: `${title} {input}`,
    model: 'v/writer',
    role: '',
    allowed_tools: null,
  };
}

function result(source: PipelineStep, output: string): StepResult {
  return {
    step_order: source.order,
    stage: source.stage,
    title: source.title,
    model: source.model,
    input_used: 'bottle',
    output,
    is_output: source.is_output,
    tool_calls: [],
  };
}

const steps = [
  step(1, 1, 'Key facts', false),
  step(2, 2, 'Tweet', true),
  step(3, 2, 'Email', true),
];
const results = [
  result(steps[0], 'Facts text'),
  result(steps[1], 'Tweet text'),
  result(steps[2], 'Email text'),
];

function renderView(overrides: Partial<Parameters<typeof PipelineRunView>[0]> = {}) {
  return render(
    <PipelineRunView
      steps={steps}
      results={results}
      isRunning={false}
      input="bottle"
      elapsedMs={2500}
      {...overrides}
    />,
  );
}

describe('PipelineRunView', () => {
  it('opens on every output with run stats, leaving intermediate work out', () => {
    renderView();
    expect(screen.getByRole('tab', { name: 'Outputs (2)' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByText('Tweet text')).toBeInTheDocument();
    expect(screen.getByText('Email text')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Stage 2 outputs' })).toContainElement(
      screen.getByText('Tweet text'),
    );
    expect(screen.queryByText('Facts text')).not.toBeInTheDocument();
    expect(screen.getByText('2 outputs · 3 steps · 2 stages · 2.5 s')).toBeInTheDocument();
  });

  it('opens intermediate work in All steps when its diagram node is clicked', async () => {
    renderView();
    await userEvent.click(screen.getByRole('button', { name: /Key facts, writer, intermediate/ }));
    expect(screen.getByRole('tab', { name: /All steps/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('Facts text')).toBeInTheDocument();
  });

  it('keeps unrun nodes inert and hides outputs before a run', () => {
    renderView({ results: [], elapsedMs: null });
    expect(screen.getByRole('button', { name: /Tweet, writer, output, Not run/ })).toBeDisabled();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('switches an output between rendered Markdown and raw text', async () => {
    renderView({ results: [result(steps[1], '**bold**')] });
    expect(screen.getByText('bold').tagName).toBe('STRONG');
    await userEvent.click(screen.getByRole('button', { name: 'Raw' }));
    expect(screen.getByText('**bold**')).toBeInTheDocument();
  });

  it('groups deliverables from separate stages', () => {
    const staged = [result({ ...steps[0], is_output: true }, 'Facts text'), ...results.slice(1)];
    renderView({ results: staged });
    expect(screen.getByRole('region', { name: 'Stage 1 outputs' })).toContainElement(
      screen.getByText('Facts text'),
    );
    expect(screen.getByRole('region', { name: 'Stage 2 outputs' })).toContainElement(
      screen.getByText('Email text'),
    );
  });

  it('shows tool call names and outcomes in All steps', async () => {
    const traced = result(steps[0], 'Facts text');
    traced.tool_calls = [
      { name: 'mcp_search', status: 'success' },
      { name: 'mcp_fetch', status: 'error' },
    ];
    renderView({ results: [traced, ...results.slice(1)] });
    await userEvent.click(screen.getByRole('tab', { name: /All steps/ }));
    await userEvent.click(screen.getByText('Tools used (2)'));
    expect(screen.getByText('mcp_search')).toBeInTheDocument();
    expect(screen.getByText('mcp_fetch')).toBeInTheDocument();
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('lets an unrun diagram add parallel work and a following stage', async () => {
    const addParallel = vi.fn();
    const addAfter = vi.fn();
    renderView({ results: [], elapsedMs: null, onAddParallel: addParallel, onAddAfter: addAfter });
    await userEvent.click(screen.getAllByRole('button', { name: '+ Parallel step' })[0]);
    await userEvent.click(screen.getAllByRole('button', { name: '+ Next stage' })[0]);
    expect(addParallel).toHaveBeenCalledWith(1);
    expect(addAfter).toHaveBeenCalledWith(1);
  });
});
