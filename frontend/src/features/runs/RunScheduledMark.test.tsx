import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { RunHistoryList } from './RunHistoryList';
import { RunTriggerTag } from './RunTriggerTag';
import { RunsPage } from './RunsPage';
import { json, makeRun } from './testData';
import { summaryOf } from './useRunHistory';

const scheduled = makeRun({
  id: 12,
  pipeline_name: 'Weekly digest',
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
  trigger: 'schedule',
  schedule_id: 4,
});
const manual = makeRun({ id: 11, pipeline_name: 'Launch kit', status: 'succeeded' });
const fromChat = makeRun({
  id: 10,
  pipeline_name: 'Chat run',
  status: 'succeeded',
  trigger: 'chat',
});

describe('the Scheduled mark on runs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('marks only the runs a schedule started', () => {
    const { rerender } = render(<RunTriggerTag trigger="schedule" />);
    expect(screen.getByText('Scheduled')).toBeInTheDocument();

    rerender(<RunTriggerTag trigger="manual" />);
    expect(screen.queryByText('Scheduled')).toBeNull();
    rerender(<RunTriggerTag trigger="chat" />);
    expect(screen.queryByText('Scheduled')).toBeNull();
  });

  it('shows in the history list beside the runs’ dates', () => {
    render(
      <MemoryRouter>
        <RunHistoryList
          items={[summaryOf(scheduled), summaryOf(manual), summaryOf(fromChat)]}
          total={3}
          selectedId={null}
          loading={false}
          loadingMore={false}
          onLoadMore={() => {}}
        />
      </MemoryRouter>,
    );

    const links = screen.getAllByRole('link');
    expect(within(links[0]).getByText('Scheduled')).toBeInTheDocument();
    expect(within(links[1]).queryByText('Scheduled')).toBeNull();
    expect(within(links[2]).queryByText('Scheduled')).toBeNull();
    expect(screen.getAllByText('Scheduled')).toHaveLength(1);
  });

  it('shows in the open run’s header too, and in the list beside it', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      String(path).startsWith(`${API.runs}?`)
        ? json({ items: [summaryOf(scheduled), summaryOf(manual)], total: 2 })
        : json(scheduled),
    );

    render(
      <MemoryRouter initialEntries={['/runs/12']}>
        <Routes>
          <Route path="/runs/:runId?" element={<RunsPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const header = (await screen.findByRole('heading', { name: 'Weekly digest' })).parentElement;
    expect(within(header as HTMLElement).getByText('Scheduled')).toBeInTheDocument();
    const history = await screen.findByRole('navigation', { name: 'Run history' });
    expect(within(history).getAllByText('Scheduled')).toHaveLength(1);
  });
});
