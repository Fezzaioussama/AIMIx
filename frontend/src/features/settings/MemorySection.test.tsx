import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Memory } from '../../core/api/memoryTypes';
import { json } from './testData';
import { renderSettingsPage } from './testRender';

const MEMORY: Memory = {
  instructions: 'We sell bread.',
  updated_at: '2026-11-06T08:30:00Z',
  max_chars: 4000,
};

/** A fetch stand-in for the Memory tab: GET answers `memory`, PUT echoes the text or answers `onPut`. */
function serve(memory = MEMORY, onPut?: (body: { instructions: string }) => Response) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path =
        typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
      if (path !== API.memory) return json({ error: 'not_found', detail: 'Not found.' }, 404);
      if (init?.method !== 'PUT') return json(memory);
      const body = JSON.parse(String(init.body)) as { instructions: string };
      return onPut ? onPut(body) : json({ ...memory, instructions: body.instructions });
    });
}

describe('MemorySection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('shows what is kept in mind, and the room left', async () => {
    serve();
    renderSettingsPage('/settings/memory');

    expect(await screen.findByLabelText('Your instructions')).toHaveValue('We sell bread.');
    expect(screen.getByText(/14 \/ 4,000 characters/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save memory' })).toBeDisabled();
  });

  it('saves the edited text and says so', async () => {
    const fetchMock = serve();
    renderSettingsPage('/settings/memory');
    const field = await screen.findByLabelText('Your instructions');

    await userEvent.clear(field);
    await userEvent.type(field, 'We sell bread and cakes.');
    await userEvent.click(screen.getByRole('button', { name: 'Save memory' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Memory saved.');
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT');
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      instructions: 'We sell bread and cakes.',
    });
    expect(screen.getByRole('button', { name: 'Save memory' })).toBeDisabled();
  });

  it('says why the text could not be saved', async () => {
    const refusal = 'Your memory can hold up to 4,000 characters; this is 4,001.';
    serve(MEMORY, () => json({ error: 'validation_error', detail: refusal }, 400));
    renderSettingsPage('/settings/memory');
    const field = await screen.findByLabelText('Your instructions');

    await userEvent.type(field, ' More.');
    await userEvent.click(screen.getByRole('button', { name: 'Save memory' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(refusal);
  });
});
