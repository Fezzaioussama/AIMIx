import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PipelineStep, RunStep } from '../../core/api/types';
import { runStep } from '../runs/testData';
import { preview, TeamRoster } from './TeamRoster';

function agent(order: number, stage: number, role: string, title: string): PipelineStep {
  return {
    order,
    stage,
    title,
    role,
    prompt: '{input}',
    model: 'deepseek/deepseek-v4-flash',
    expected_output: '',
    allowed_tools: [],
    is_output: false,
    condition: null,
    review: null,
  };
}

const RESEARCH = agent(1, 1, 'Researcher', 'App facts');
const EMAIL = { ...agent(2, 2, 'Copywriter', 'Launch email'), is_output: true };
const POSTS = { ...agent(3, 2, 'Social writer', 'Three posts'), is_output: true };
const CHECK = {
  ...agent(4, 3, 'Orchestrator', 'Final check'),
  review: { send_back_to_stage: 2, max_rounds: 2 },
};
const TEAM = [RESEARCH, EMAIL, POSTS, CHECK];

function live(step: PipelineStep, overrides: Partial<RunStep>): RunStep {
  return {
    ...runStep(1, 'succeeded'),
    step_order: step.order,
    stage: step.stage,
    title: step.title,
    is_output: step.is_output,
    ...overrides,
  };
}

describe('TeamRoster', () => {
  it('lists the agents by step, the ones of a step working together, each by role and work', () => {
    render(<TeamRoster steps={TEAM} runActive={false} selected={null} />);

    const team = screen.getByRole('list', { name: 'Your team' });
    expect(within(team).getByText('Step 1')).toBeInTheDocument();
    expect(within(team).getByText('Step 2 · together')).toBeInTheDocument();
    expect(
      screen.getByRole('group', { name: 'Launch email, Copywriter, deliverable, Not run' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('Deliverable')).toHaveLength(2);
    expect(screen.getByText('Checks the work')).toBeInTheDocument();
    // Read-only: nothing to open while no edit is offered.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('follows a run: who works now, who is done with the start of their work', () => {
    const steps = [
      live(RESEARCH, { output: '## Facts\n\n**Plantly** reminds you to water each plant' }),
      live(EMAIL, { status: 'running', output: '' }),
      live(POSTS, { status: 'pending', output: '' }),
      live(CHECK, { status: 'pending', output: '' }),
    ];

    render(<TeamRoster steps={TEAM} liveSteps={steps} runActive selected={null} />);

    expect(
      screen.getByRole('group', { name: /App facts, Researcher, intermediate, Done/ }),
    ).toHaveTextContent('Facts Plantly reminds you to water each plant');
    expect(screen.getByRole('group', { name: /Launch email, .*, Running/ })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Three posts, .*, Waiting/ })).toBeInTheDocument();
  });

  it('tells what a check decided, and its round', () => {
    const steps = [live(CHECK, { rounds: 2, verdict: 'pass', output: 'All good.' })];

    render(<TeamRoster steps={TEAM} liveSteps={steps} runActive={false} selected={null} />);

    expect(
      screen.getByRole('group', {
        name: 'Final check, Orchestrator, intermediate, Done · Round 2 of 3 · Sent back 1 time, then approved',
      }),
    ).toBeInTheDocument();
  });

  it('opens an agent for editing when the team can be edited', async () => {
    const onEditStep = vi.fn();
    render(<TeamRoster steps={TEAM} runActive={false} selected={2} onEditStep={onEditStep} />);

    const email = screen.getByRole('button', { name: /Launch email, Copywriter/ });
    expect(email).toHaveClass('ring-2');
    await userEvent.click(email);

    expect(onEditStep).toHaveBeenCalledWith(2);
  });
});

describe('preview', () => {
  it('reads Markdown as plain words and cuts a long text', () => {
    expect(preview('# Title\n\n| a | b |\n**bold** `code`')).toBe('Title a b bold code');
    expect(preview('word '.repeat(80))).toMatch(/…$/);
    expect(preview('word '.repeat(80)).length).toBeLessThanOrEqual(161);
  });
});
