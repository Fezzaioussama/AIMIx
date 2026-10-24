import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PipelineInput } from '../../core/api/types';
import { RunInputCard } from './RunInputCard';
import { EMPTY_RUN_DRAFT, type RunDraft } from './pipelineInputs';

const inputs: PipelineInput[] = [
  { name: 'topic', label: 'Topic', description: 'What the posts are about' },
  { name: 'audience', label: '', description: '' },
];

function Harness({ declared, onRun }: { declared: PipelineInput[]; onRun: () => void }) {
  const [draft, setDraft] = useState<RunDraft>(EMPTY_RUN_DRAFT);
  return (
    <RunInputCard
      inputs={declared}
      draft={draft}
      isRunning={false}
      dirty={false}
      isSaved
      message=""
      onDraftChange={setDraft}
      onRun={onRun}
    />
  );
}

describe('RunInputCard', () => {
  it('asks for each named input and runs once all are filled', async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    render(<Harness declared={inputs} onRun={onRun} />);
    const run = screen.getByRole('button', { name: 'Run Pipeline' });

    await user.type(screen.getByRole('textbox', { name: /Topic/ }), 'bees');
    expect(run).toBeDisabled();
    expect(screen.getByPlaceholderText('What the posts are about')).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: /audience/ }), 'kids');
    await user.click(run);
    expect(onRun).toHaveBeenCalledOnce();
  });

  it('keeps one free-text field for a pipeline without named inputs', async () => {
    const user = userEvent.setup();
    render(<Harness declared={[]} onRun={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeDisabled();

    await user.type(screen.getByRole('textbox', { name: 'Run input' }), 'seed');

    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeEnabled();
  });
});
