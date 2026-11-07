import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { ShareRunButton } from './ShareRunButton';
import { json } from './testData';

const LINK = {
  token: 'tok-1',
  url: 'https://aimix.example/shared/tok-1',
  created_at: '2026-10-24T10:00:00Z',
};

describe('ShareRunButton', () => {
  afterEach(() => vi.restoreAllMocks());

  it('offers Share while the run has no link, then shows the link with Copy and Stop sharing', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (_path, init) =>
        init?.method === 'POST'
          ? json(LINK)
          : init?.method === 'DELETE'
            ? new Response(null, { status: 204 })
            : json(null),
      );
    render(<ShareRunButton runId={7} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Share' }));

    const group = await screen.findByRole('group', { name: 'Share link' });
    expect(group).toHaveTextContent(`${window.location.origin}/shared/tok-1`);
    expect(group).toHaveTextContent('Anyone with the link can read this report');
    await userEvent.click(screen.getByRole('button', { name: 'Stop sharing' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Share' })).toBeInTheDocument());
    expect(fetchMock.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      [API.runShare(7), 'GET'],
      [API.runShare(7), 'POST'],
      [API.runShare(7), 'DELETE'],
    ]);
  });

  it('shows a link the run already has, and says why sharing failed', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) =>
      init?.method === 'DELETE'
        ? json({ error: 'conflict', detail: 'Share the run once it has ended.' }, 409)
        : json(LINK),
    );
    render(<ShareRunButton runId={7} />);

    expect(await screen.findByRole('group', { name: 'Share link' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Stop sharing' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Share the run once it has ended.');
  });
});
