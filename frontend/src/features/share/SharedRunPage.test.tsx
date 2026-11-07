import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json, makeRun, runStep } from '../runs/testData';
import { useReportSpec } from '../runs/report/testReport';
import { NOT_SHARED, SharedRunPage } from './SharedRunPage';

/** The report a link shows: inputs, prompts and the owner's things already stripped. */
const SHARED = makeRun({
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
  input: '',
  steps: [
    runStep(1, 'succeeded', 'Research notes'),
    runStep(2, 'succeeded', 'The launch plan'),
    runStep(3, 'succeeded', 'A summary'),
  ],
});

function renderPage(token = 'tok-1') {
  return render(
    <MemoryRouter initialEntries={[`/shared/${token}`]}>
      <Routes>
        <Route path="/shared/:token" element={<SharedRunPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SharedRunPage', () => {
  useReportSpec();

  it('shows the report read-only, with nothing to act on or rate', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(SHARED));
    renderPage();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Launch kit' }),
    ).toBeInTheDocument();
    expect(screen.getByText('The launch plan')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop|Resume|Delete|Share/ })).toBeNull();
    expect(screen.queryByText('Was this useful?')).toBeNull();
    expect(screen.queryByText('Open in Runs')).toBeNull();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([API.sharedRun('tok-1')]);
  });

  it('says when a link shows nothing', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json({ error: 'not_found', detail: NOT_SHARED }, 404),
    );
    renderPage('gone');

    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_SHARED);
  });
});
