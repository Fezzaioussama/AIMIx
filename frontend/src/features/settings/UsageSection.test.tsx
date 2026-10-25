import { render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { UsageReport } from '../../core/api/types';
import { SettingsPage } from './SettingsPage';
import { UsageSection } from './UsageSection';
import { SETTINGS, byPath, json } from './testData';
import { USAGE_DAYS, useUsage } from './useUsage';

const USAGE_PATH = `${API.usage}?days=${USAGE_DAYS}`;

const REPORT: UsageReport = {
  days: 30,
  since: '2026-09-25T10:00:00Z',
  runs: 12,
  usage: { input_tokens: 100_000, output_tokens: 23_456, cost_usd: 1.234, cost_complete: true },
  pipelines: [
    {
      pipeline_id: 3,
      pipeline_name: 'Launch kit',
      runs: 8,
      usage: { input_tokens: 90_000, output_tokens: 20_000, cost_usd: 1.2, cost_complete: true },
    },
    {
      pipeline_id: null,
      pipeline_name: 'Old idea',
      runs: 1,
      usage: { input_tokens: 10_000, output_tokens: 3_456, cost_usd: 0.034, cost_complete: true },
    },
  ],
};

function serve(report: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(byPath({ [USAGE_PATH]: report }));
}

describe('UsageSection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows the last 30 days: runs, cost and tokens, then each pipeline', async () => {
    serve(REPORT);
    render(<UsageSection />);

    expect(screen.getByText('Loading your usage…')).toBeInTheDocument();
    const section = await screen.findByRole('region', { name: 'Usage' });
    expect(within(section).getByText(/last 30 days/)).toBeInTheDocument();

    const stats = within(section)
      .getAllByRole('term')
      .map((term) => term.textContent);
    expect(stats).toEqual(['Runs', 'Cost', 'Tokens']);
    expect(within(section).getByText('12')).toBeInTheDocument();
    expect(within(section).getByText('$1.23')).toHaveAttribute(
      'title',
      '100,000 tokens in, 23,456 out',
    );
    expect(within(section).getByText('123,456')).toBeInTheDocument();
    expect(within(section).getByText('100,000 tokens in, 23,456 out')).toBeInTheDocument();

    const rows = within(screen.getByRole('list', { name: 'Usage by pipeline' })).getAllByRole(
      'listitem',
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Launch kit');
    expect(rows[0]).toHaveTextContent('8 runs · 110,000 tokens');
    expect(rows[0]).toHaveTextContent('$1.20');
    expect(rows[1]).toHaveTextContent('Old idea(deleted)');
    expect(rows[1]).toHaveTextContent('1 run · 13,456 tokens');
    expect(screen.queryByText(/real cost is higher/)).not.toBeInTheDocument();
  });

  it('asks the server for those days, once', async () => {
    const fetchMock = serve(REPORT);
    render(<UsageSection />);
    await screen.findByRole('list', { name: 'Usage by pipeline' });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/usage?days=30');
  });

  it('says so when there were no runs', async () => {
    serve({
      ...REPORT,
      runs: 0,
      usage: { ...REPORT.usage, input_tokens: 0, output_tokens: 0, cost_usd: null },
      pipelines: [],
    });
    render(<UsageSection />);

    expect(await screen.findByText('No runs in the last 30 days.')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Usage by pipeline' })).not.toBeInTheDocument();
  });

  it('is plain that a cost is a floor when some model has no known cost', async () => {
    serve({
      ...REPORT,
      usage: { ...REPORT.usage, cost_complete: false },
      pipelines: [
        {
          pipeline_id: 4,
          pipeline_name: 'Unpriced',
          runs: 2,
          usage: { input_tokens: 500, output_tokens: 100, cost_usd: null, cost_complete: false },
        },
      ],
    });
    render(<UsageSection />);

    expect(await screen.findByText('$1.23+')).toBeInTheDocument();
    expect(screen.getByText('Cost unknown')).toBeInTheDocument();
    expect(
      screen.getByText('Some runs used models whose cost is unknown, so the real cost is higher.'),
    ).toBeInTheDocument();
  });

  it('tells the person when the usage could not be loaded', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: 'server_error', detail: 'Something broke on our side.' }, 500),
    );
    render(<UsageSection />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Something broke on our side.');
    expect(screen.queryByText('Loading your usage…')).not.toBeInTheDocument();
  });

  it('is part of the Settings page', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      byPath({ [API.llmSettings]: SETTINGS, [API.integrations]: [], [USAGE_PATH]: REPORT }),
    );
    render(<SettingsPage />);

    expect(await screen.findByRole('heading', { name: 'Usage' })).toBeInTheDocument();
    expect(await screen.findByText('Launch kit')).toBeInTheDocument();
  });
});

describe('useUsage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('cancels its request when the screen goes away, and sets no state after', async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_path, init) =>
        new Promise((_resolve, reject) => {
          signal = init?.signal ?? undefined;
          signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          );
        }),
    );
    const { result, unmount } = renderHook(() => useUsage(USAGE_DAYS));
    await waitFor(() => expect(signal).toBeDefined());
    expect(result.current.loading).toBe(true);

    unmount();

    expect(signal?.aborted).toBe(true);
  });

  it('loads the report and stops loading', async () => {
    serve(REPORT);
    const { result } = renderHook(() => useUsage(USAGE_DAYS));

    await waitFor(() => expect(result.current.report).toEqual(REPORT));
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBe('');
  });
});
