import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ExtractedDocument, PipelineInput } from '../../core/api/types';
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

  describe('attaching a document', () => {
    const report: ExtractedDocument = {
      filename: 'report.pdf',
      format: 'pdf',
      text: 'Revenue grew.',
      characters: 13,
      pages: 2,
      truncated: false,
    };
    const reply = () => new Response(JSON.stringify(report), { status: 200 });
    const pdf = () => new File(['%PDF'], 'report.pdf', { type: 'application/pdf' });

    afterEach(() => vi.restoreAllMocks());

    it('fills the free-text input from a document, after what was already typed', async () => {
      const user = userEvent.setup();
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply());
      render(<Harness declared={[]} onRun={vi.fn()} />);
      await user.type(screen.getByRole('textbox', { name: 'Run input' }), 'Summarise this:');

      await user.upload(screen.getByLabelText('Attach a document'), pdf());

      expect(screen.getByRole('textbox', { name: 'Run input' })).toHaveValue(
        'Summarise this:\n\n[Document: report.pdf]\nRevenue grew.',
      );
      expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeEnabled();
    });

    it('offers a document for each named input and fills only that one', async () => {
      const user = userEvent.setup();
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(reply());
      render(<Harness declared={inputs} onRun={vi.fn()} />);

      const [topicAttach] = screen.getAllByLabelText('Attach a document');
      expect(screen.getAllByLabelText('Attach a document')).toHaveLength(inputs.length);
      await user.upload(topicAttach, pdf());

      expect(screen.getByRole('textbox', { name: /Topic/ })).toHaveValue(
        '[Document: report.pdf]\nRevenue grew.',
      );
      expect(screen.getByRole('textbox', { name: /audience/ })).toHaveValue('');
      expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeDisabled();
    });

    it('keeps what was typed while a large document was being read', async () => {
      const user = userEvent.setup();
      let finish: (response: Response) => void = () => {};
      vi.spyOn(globalThis, 'fetch').mockReturnValue(
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
      );
      render(<Harness declared={[]} onRun={vi.fn()} />);

      await user.upload(screen.getByLabelText('Attach a document'), pdf());
      await user.type(screen.getByRole('textbox', { name: 'Run input' }), 'typed meanwhile');
      finish(reply());

      await waitFor(() =>
        expect(screen.getByRole('textbox', { name: 'Run input' })).toHaveValue(
          'typed meanwhile\n\n[Document: report.pdf]\nRevenue grew.',
        ),
      );
    });
  });
});
