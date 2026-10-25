import { useState } from 'react';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { PipelineInput } from '../../core/api/types';
import { RunInputCard } from './RunInputCard';
import { EMPTY_RUN_DRAFT, costLimitProblem, isRunReady, runRequest } from './pipelineInputs';
import type { RunDraft } from './pipelineInputs';
import { usePipelineBuilder } from './usePipelineBuilder';

const topic: PipelineInput = { name: 'topic', label: 'Topic', description: '' };

function Harness({ onRun }: { onRun: () => void }) {
  const [draft, setDraft] = useState<RunDraft>({ ...EMPTY_RUN_DRAFT, text: 'seed' });
  return (
    <RunInputCard
      inputs={[]}
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

describe('the cost limit of a run, as a draft', () => {
  it('is optional: empty or missing means no limit of its own', () => {
    expect(costLimitProblem({ text: 'go', values: {} })).toBeNull();
    expect(costLimitProblem({ text: 'go', values: {}, maxCost: '  ' })).toBeNull();
    expect(runRequest([], { text: 'go', values: {}, maxCost: '' })).toEqual({ input: 'go' });
  });

  it('goes with the run, as dollars, whichever way the inputs are given', () => {
    expect(runRequest([], { text: 'go', values: {}, maxCost: '$0.50' })).toEqual({
      input: 'go',
      max_cost_usd: 0.5,
    });
    expect(runRequest([topic], { text: '', values: { topic: 'bees' }, maxCost: '2' })).toEqual({
      inputs: { topic: 'bees' },
      max_cost_usd: 2,
    });
  });

  it('refuses to run on a limit that is typed but not usable', () => {
    for (const maxCost of ['0', '-1', 'cheap', '1e3']) {
      expect(costLimitProblem({ text: 'go', values: {}, maxCost })).toBe(
        'Enter an amount above zero, like 0.50, or leave it empty.',
      );
      expect(isRunReady([], { text: 'go', values: {}, maxCost })).toBe(false);
    }
    expect(isRunReady([], { text: 'go', values: {}, maxCost: '0.50' })).toBe(true);
  });
});

describe('RunInputCard cost limit', () => {
  it('has a labelled, optional "Stop if it costs more than" field', () => {
    render(<Harness onRun={vi.fn()} />);

    const field = screen.getByRole('textbox', { name: /Stop if it costs more than/ });
    expect(field).toHaveValue('');
    expect(screen.getByText('(optional)')).toBeInTheDocument();
    expect(field).toHaveAccessibleDescription(
      'The run stops by itself once the model calls cost this much.',
    );
  });

  it('runs without a limit when the field is left empty', async () => {
    const onRun = vi.fn();
    render(<Harness onRun={onRun} />);

    await userEvent.click(screen.getByRole('button', { name: 'Run Pipeline' }));

    expect(onRun).toHaveBeenCalledOnce();
  });

  it('keeps what was typed and still runs', async () => {
    const onRun = vi.fn();
    render(<Harness onRun={onRun} />);

    await userEvent.type(screen.getByRole('textbox', { name: /Stop if it costs/ }), '0.50');
    await userEvent.click(screen.getByRole('button', { name: 'Run Pipeline' }));

    expect(screen.getByRole('textbox', { name: /Stop if it costs/ })).toHaveValue('0.50');
    expect(onRun).toHaveBeenCalledOnce();
  });

  it('says what is wrong and blocks the run, instead of running without the cap', async () => {
    const onRun = vi.fn();
    render(<Harness onRun={onRun} />);
    const field = screen.getByRole('textbox', { name: /Stop if it costs/ });

    await userEvent.type(field, 'cheap');

    expect(field).toBeInvalid();
    expect(field).toHaveAccessibleDescription(
      'Enter an amount above zero, like 0.50, or leave it empty.',
    );
    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeDisabled();

    await userEvent.clear(field);
    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeEnabled();
  });
});

describe('usePipelineBuilder cost limit', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts the run with the typed limit', async () => {
    const saved = { id: 7, name: 'Posts', inputs: [], steps: [] };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify([saved]), { headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 12, status: 'queued' }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model', 7));
    await waitFor(() => expect(result.current.pipeline.id).toBe(7));

    await act(async () => {
      await result.current.actions.run({ text: 'go', values: {}, maxCost: '0.75' });
    });

    expect(fetchMock.mock.calls[1][0]).toBe(API.pipelineRuns(7));
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"input":"go","max_cost_usd":0.75}');
  });
});
