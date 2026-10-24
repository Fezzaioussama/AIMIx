import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { RunsPage } from './RunsPage';
import { json, makeRun, runStep } from './testData';
import { summaryOf as summary } from './useRunHistory';

const finished = makeRun({
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
  steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'succeeded', 'b'), runStep(3, 'succeeded', 'c')],
});
const older = makeRun({ id: 6, pipeline_name: 'Weekly digest', status: 'failed' });

function serveHistory() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (path, init) => {
    if (init?.method === 'DELETE') return new Response(null, { status: 204 });
    if (String(path).startsWith(`${API.runs}?`)) {
      return json({ items: [summary(finished), summary(older)], total: 2 });
    }
    if (path === API.run(finished.id)) return json(finished);
    return json({ error: 'not_found', detail: 'Missing.' }, 404);
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/runs/:runId?" element={<RunsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RunsPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists every run with its status and opens one from the list', async () => {
    serveHistory();
    renderAt('/runs');

    const history = await screen.findByRole('navigation', { name: 'Run history' });
    expect(within(history).getByText('Weekly digest')).toBeInTheDocument();
    expect(within(history).getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText('Choose a run to see its steps and results.')).toBeInTheDocument();

    await userEvent.click(within(history).getByRole('link', { name: /Launch kit/ }));

    expect(await screen.findByRole('heading', { name: 'Launch kit' })).toBeInTheDocument();
    expect(within(history).getByRole('link', { name: /Launch kit/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('deletes a finished run only after a confirmation', async () => {
    const fetchMock = serveHistory();
    renderAt(`/runs/${finished.id}`);
    await screen.findByRole('heading', { name: 'Launch kit' });

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const confirm = screen.getByRole('group', { name: 'Confirm delete' });
    expect(within(confirm).getByRole('button', { name: 'Keep' })).toHaveFocus();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false);

    await userEvent.click(within(confirm).getByRole('button', { name: 'Yes, delete' }));

    expect(
      await screen.findByText('Choose a run to see its steps and results.'),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      API.run(finished.id),
      expect.objectContaining({ method: 'DELETE' }),
    );
    const history = screen.getByRole('navigation', { name: 'Run history' });
    expect(within(history).queryByText('Launch kit')).not.toBeInTheDocument();
  });

  it('offers no delete while a run is still going', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      String(path).startsWith(`${API.runs}?`)
        ? json({ items: [summary(makeRun())], total: 1 })
        : json(makeRun()),
    );
    renderAt('/runs/7');

    expect(await screen.findByRole('button', { name: 'Stop' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
  });
});
