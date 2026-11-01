import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ExtractedDocument, PipelineInput } from '../../core/api/types';
import { RunInputCard } from './RunInputCard';
import { EMPTY_RUN_DRAFT, RUN_INPUT_MAX_LENGTH, type RunDraft } from './pipelineInputs';

const inputs: PipelineInput[] = [
  { name: 'topic', label: 'Topic', description: 'What the posts are about' },
  { name: 'audience', label: '', description: '' },
];

function Harness({
  declared,
  onRun,
  initial = EMPTY_RUN_DRAFT,
}: {
  declared: PipelineInput[];
  onRun: () => void;
  initial?: RunDraft;
}) {
  const [draft, setDraft] = useState<RunDraft>(initial);
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

    it('offers a document and a web page for each named input', () => {
      render(<Harness declared={inputs} onRun={vi.fn()} />);

      expect(screen.getAllByLabelText('Attach a document')).toHaveLength(inputs.length);
      expect(screen.getAllByRole('button', { name: 'Add a web page' })).toHaveLength(inputs.length);
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

    it('waits for a document still being read before it runs', async () => {
      const user = userEvent.setup();
      let finish: (response: Response) => void = () => {};
      vi.spyOn(globalThis, 'fetch').mockReturnValue(
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
      );
      render(<Harness declared={inputs} onRun={vi.fn()} />);
      await user.type(screen.getByRole('textbox', { name: /Topic/ }), 'bees');
      await user.type(screen.getByRole('textbox', { name: /audience/ }), 'kids');

      await user.upload(screen.getAllByLabelText('Attach a document')[1], pdf());

      const run = screen.getByRole('button', { name: 'Run Pipeline' });
      expect(run).toBeDisabled();
      expect(screen.getByText('Waiting for report.pdf to be read…')).toBeInTheDocument();

      finish(reply());

      await waitFor(() => expect(run).toBeEnabled());
      expect(screen.queryByText(/^Waiting for/)).not.toBeInTheDocument();
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

  describe('the run’s limit', () => {
    afterEach(() => vi.restoreAllMocks());

    it('will not run inputs past it, and says why', () => {
      const tooLong = { text: 'x'.repeat(612_000), values: {} };
      render(<Harness declared={[]} onRun={vi.fn()} initial={tooLong} />);

      expect(
        screen.getByText(
          'Your inputs are 612,000 characters; a run takes at most 500,000. ' +
            'Shorten the text, or delete a document from it (each starts with “[Document: …]”).',
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeDisabled();
    });

    it('says so in a live region that is there before the text is too long', () => {
      render(<Harness declared={[]} onRun={vi.fn()} />);
      const regions = screen.getAllByRole('status');

      fireEvent.change(screen.getByRole('textbox', { name: 'Run input' }), {
        target: { value: 'x'.repeat(RUN_INPUT_MAX_LENGTH + 1) },
      });

      // A region added already filled is often not announced.
      expect(screen.getAllByRole('status')).toEqual(regions);
      expect(regions.some((region) => /500,001 characters/.test(region.textContent ?? ''))).toBe(
        true,
      );
    });

    it('counts every input when a document is attached to one of them', async () => {
      const user = userEvent.setup();
      const report: ExtractedDocument = {
        filename: 'report.pdf',
        format: 'pdf',
        text: 'Revenue grew.',
        characters: 13,
        pages: 2,
        truncated: false,
      };
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(report), { status: 200 }),
      );
      const nearlyFull = { text: '', values: { topic: 'x'.repeat(RUN_INPUT_MAX_LENGTH - 10) } };
      render(<Harness declared={inputs} onRun={vi.fn()} initial={nearlyFull} />);

      await user.upload(
        screen.getAllByLabelText('Attach a document')[1],
        new File(['%PDF'], 'report.pdf'),
      );

      expect(await screen.findByRole('alert')).toHaveTextContent(
        'Adding report.pdf would make your inputs 500,026 characters',
      );
      expect(screen.getByRole('textbox', { name: /audience/ })).toHaveValue('');
    });
  });
});
