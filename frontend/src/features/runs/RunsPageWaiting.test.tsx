import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Run } from '../../core/api/types';
import { RunsPage } from './RunsPage';
import { json, makeApproval, makeRun, runStep } from './testData';
import { summaryOf } from './useRunHistory';

const waiting = makeRun({
  status: 'waiting',
  steps: [runStep(1, 'succeeded', 'Research notes'), runStep(2, 'running'), runStep(3, 'pending')],
  pending_approvals: [makeApproval()],
});
const going = makeRun({ steps: waiting.steps });
const CARD = { name: 'Allow “Send email”?' };

/** The server as the page sees it: the run changes when an answer is posted. */
function serve(answer: (path: string) => Response | null = () => null) {
  let run: Run = waiting;
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
    const url = String(path);
    const refused = answer(url);
    if (refused) return refused;
    if (url === API.approveToolCall(7, 31) || url === API.declineToolCall(7, 31)) {
      run = going;
      return json(run);
    }
    if (url.includes('status=waiting')) {
      return json({ items: [], total: run.status === 'waiting' ? 1 : 0 });
    }
    if (url.startsWith(`${API.runs}?`)) return json({ items: [summaryOf(run)], total: 1 });
    return url === API.run(7) ? json(run) : json({ error: 'not_found', detail: 'Missing.' }, 404);
  });
  return fetchMock;
}

function renderRun() {
  return render(
    <MemoryRouter initialEntries={['/runs/7']}>
      <Routes>
        <Route path="/runs/:runId?" element={<RunsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RunsPage with a run that waits for you', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows it in the history, on the Runs tab and in its own header', async () => {
    serve();
    renderRun();

    const history = await screen.findByRole('navigation', { name: 'Run history' });
    expect(within(history).getByText('Waiting for you')).toBeInTheDocument();
    expect(within(history).getByText('Needs your OK')).toBeInTheDocument();
    expect(
      await screen.findByRole('link', { name: 'Runs, 1 waiting for you' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Run waiting for you. 1 of 3 steps done.')).toBeInTheDocument();
    expect(screen.getByRole('region', CARD)).toBeVisible();
  });

  it('lets the run go on once the request is approved', async () => {
    const user = userEvent.setup();
    const fetchMock = serve();
    renderRun();

    await user.click(
      within(await screen.findByRole('region', CARD)).getByRole('button', { name: 'Approve' }),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      API.approveToolCall(7, 31),
      expect.objectContaining({ method: 'POST' }),
    );
    await waitFor(() => expect(screen.queryByRole('region', CARD)).not.toBeInTheDocument());
    const history = screen.getByRole('navigation', { name: 'Run history' });
    expect(within(history).getByText('Running')).toBeInTheDocument();
    expect(screen.queryByText('Needs your OK')).not.toBeInTheDocument();
  });

  it('declines a request too', async () => {
    const user = userEvent.setup();
    const fetchMock = serve();
    renderRun();

    await user.click(
      within(await screen.findByRole('region', CARD)).getByRole('button', { name: 'Decline' }),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      API.declineToolCall(7, 31),
      expect.objectContaining({ method: 'POST' }),
    );
    await waitFor(() => expect(screen.queryByRole('region', CARD)).not.toBeInTheDocument());
  });

  it('says why an answer was refused and leaves the request to answer again', async () => {
    const user = userEvent.setup();
    serve((url) =>
      url === API.approveToolCall(7, 31)
        ? json({ error: 'conflict', detail: 'This request has expired.' }, 409)
        : null,
    );
    renderRun();

    await user.click(
      within(await screen.findByRole('region', CARD)).getByRole('button', { name: 'Approve' }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('This request has expired.');
    expect(screen.getByRole('region', CARD)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled();
  });
});
