import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { AgentTool, PipelineStep } from '../../core/api/types';
import { StepAgentFields } from './StepAgentFields';

const tools: AgentTool[] = [
  { name: 'list_pipelines', source: 'AIMIx', description: 'List saved pipelines' },
  { name: 'mcp_search', source: 'Search MCP', description: 'Search the web' },
];

const integrationTools: AgentTool[] = [
  ...tools,
  { name: 'crm_find_contact', source: 'crm', description: 'Find a contact' },
  { name: 'calculator', source: 'AIMIx', description: 'Do arithmetic' },
];

function Harness({ catalog = tools }: { catalog?: AgentTool[] }) {
  const [step, setStep] = useState<PipelineStep>({
    order: 1,
    stage: 1,
    title: '',
    is_output: false,
    expected_output: '',
    prompt: 'Work',
    model: 'v/m',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  });
  return (
    <>
      <StepAgentFields
        step={step}
        tools={catalog}
        onChange={(patch) => setStep((current) => ({ ...current, ...patch }))}
      />
      <output data-testid="step-config">
        {JSON.stringify({ role: step.role, allowed_tools: step.allowed_tools })}
      </output>
    </>
  );
}

describe('StepAgentFields', () => {
  it('supports all, a selected subset, and no tools while editing the role', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByRole('button', { name: 'All tools' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await user.click(screen.getByText('Choose tools · All configured tools'));
    await user.click(screen.getByRole('checkbox', { name: /mcp_search/ }));
    expect(screen.getByTestId('step-config')).toHaveTextContent(
      '"allowed_tools":["list_pipelines"]',
    );

    await user.click(screen.getByRole('button', { name: 'No tools' }));
    expect(screen.getByTestId('step-config')).toHaveTextContent('"allowed_tools":[]');

    await user.click(screen.getByRole('button', { name: 'All tools' }));
    await user.type(screen.getByRole('textbox', { name: 'Agent role' }), 'Researcher');
    expect(screen.getByTestId('step-config')).toHaveTextContent('"role":"Researcher"');
    expect(screen.getByTestId('step-config')).toHaveTextContent('"allowed_tools":null');
  });

  it('groups tools by where they come from, each integration under its name', async () => {
    const user = userEvent.setup();
    render(<Harness catalog={integrationTools} />);

    await user.click(screen.getByText('Choose tools · All configured tools'));

    const builtIn = screen.getByRole('group', { name: 'AIMIx tools' });
    expect(within(builtIn).getAllByRole('checkbox')).toHaveLength(2);
    const crm = screen.getByRole('group', { name: 'crm tools' });
    expect(within(crm).getByRole('checkbox', { name: /crm_find_contact/ })).toBeChecked();
  });
});
