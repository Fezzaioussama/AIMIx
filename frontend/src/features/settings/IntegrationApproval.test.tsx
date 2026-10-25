import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { IntegrationsSection } from './IntegrationsSection';
import { INTEGRATION, json } from './testData';

const ONE = API.integration(INTEGRATION.id);

/** The list, and what each PATCH answers; every PATCH body is kept. */
function serve(listed = INTEGRATION) {
  const patched: unknown[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (init?.method === 'PATCH' && input === ONE) {
      const body = JSON.parse(String(init.body));
      patched.push(body);
      return json({ ...listed, ...body });
    }
    return input === API.integrations ? json([listed]) : json({ error: 'not_found' }, 404);
  });
  return patched;
}

describe('an integration asks before its tools act', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is on for a new integration, with what that means in words', async () => {
    serve();
    render(<IntegrationsSection />);

    const card = await screen.findByRole('region', { name: 'crm' });

    const asks = within(card).getByRole('switch', { name: 'Ask me before its tools act' });
    expect(asks).toBeChecked();
    expect(asks).toHaveAccessibleDescription(
      'In a run, each action waits for your OK first. Chat cannot use its tools.',
    );
  });

  it('switches off, saving only that field, and says what it now means', async () => {
    const user = userEvent.setup();
    const patched = serve();
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('switch', { name: 'Ask me before its tools act' }));

    expect(patched).toEqual([{ require_approval: false }]);
    expect(await screen.findByText('crm will act without asking you first.')).toBeInTheDocument();
    const asks = screen.getByRole('switch', { name: 'Ask me before its tools act' });
    expect(asks).not.toBeChecked();
    expect(asks).toHaveAccessibleDescription(
      'Its tools act without asking you first, in runs and in chat.',
    );
  });

  it('switches back on', async () => {
    const user = userEvent.setup();
    const patched = serve({ ...INTEGRATION, require_approval: false });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('switch', { name: 'Ask me before its tools act' }));

    expect(patched).toEqual([{ require_approval: true }]);
    expect(await screen.findByText('crm will ask you before its tools act.')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Ask me before its tools act' })).toBeChecked();
  });

  it('is its own switch: the one that lets agents use the integration stays as it was', async () => {
    const user = userEvent.setup();
    serve();
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('switch', { name: 'Ask me before its tools act' }));

    await screen.findByText('crm will act without asking you first.');
    expect(screen.getByRole('switch', { name: 'Let agents use crm' })).toBeChecked();
  });

  it('says why a change could not be saved and keeps the switch as it was', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) =>
      init?.method === 'PATCH'
        ? json({ error: 'server_error', detail: 'Try again.' }, 500)
        : json(input === API.integrations ? [INTEGRATION] : {}),
    );
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('switch', { name: 'Ask me before its tools act' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Try again.');
    expect(screen.getByRole('switch', { name: 'Ask me before its tools act' })).toBeChecked();
  });
});
