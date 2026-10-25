import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { RunSummary } from '../../core/api/types';
import { RunHistoryList } from './RunHistoryList';
import { makeRun, usageOf } from './testData';
import { summaryOf } from './useRunHistory';

const finished = {
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
} as const;

function listed(...runs: RunSummary[]) {
  return render(
    <MemoryRouter>
      <RunHistoryList
        items={runs}
        total={runs.length}
        selectedId={null}
        loading={false}
        loadingMore={false}
        onLoadMore={vi.fn()}
      />
    </MemoryRouter>,
  );
}

function row(name: string) {
  return screen.getByRole('link', { name: new RegExp(name) });
}

describe('RunHistoryList cost', () => {
  it('shows what each run cost beside how long it took', () => {
    listed(
      summaryOf(
        makeRun({ id: 3, pipeline_name: 'Priced', ...finished, usage: usageOf(1234, 567, 0.0123) }),
      ),
    );

    expect(within(row('Priced')).getByText('$0.0123')).toHaveAttribute(
      'title',
      '1,234 tokens in, 567 out',
    );
    expect(row('Priced')).toHaveTextContent('9.0 s · $0.0123');
  });

  it('says the cost is unknown when the model has no price, and marks a floor', () => {
    listed(
      summaryOf(
        makeRun({ id: 4, pipeline_name: 'Unpriced', ...finished, usage: usageOf(900, 100, null) }),
      ),
      summaryOf(
        makeRun({
          id: 5,
          pipeline_name: 'Mixed',
          ...finished,
          usage: { ...usageOf(900, 100, 0.02), cost_complete: false },
        }),
      ),
    );

    expect(within(row('Unpriced')).getByText('Cost unknown')).toBeInTheDocument();
    expect(within(row('Mixed')).getByText('$0.0200+')).toBeInTheDocument();
  });

  it('says nothing about cost for a run that has not used anything yet', () => {
    listed(summaryOf(makeRun({ id: 6, pipeline_name: 'Waiting', status: 'queued' })));

    expect(row('Waiting')).not.toHaveTextContent('$');
    expect(row('Waiting')).not.toHaveTextContent('unknown');
  });

  it('keeps a listed run up to date, cost included, from the run open beside it', () => {
    const open = makeRun({ usage: usageOf(10, 5, 0.01), max_cost_usd: 0.5, max_tokens: 900 });

    expect(summaryOf(open)).toMatchObject({
      max_cost_usd: 0.5,
      max_tokens: 900,
      usage: usageOf(10, 5, 0.01),
    });
    // A summary is the run without its steps, inputs and outputs.
    expect(summaryOf(open)).not.toHaveProperty('steps');
  });
});
