import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { IntegrationsSection } from './IntegrationsSection';
import { INTEGRATION, json } from './testData';

type Handler = (body: unknown) => Response;

/** Answers `"<METHOD> <path>"` requests; anything else is a 404. */
function serve(handlers: Record<string, Handler>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const handler = handlers[`${init?.method ?? 'GET'} ${String(input)}`];
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    return handler ? handler(body) : json({ error: 'not_found', detail: 'Not found.' }, 404);
  });
}

const LIST = `GET ${API.integrations}`;
const ONE = API.integration(INTEGRATION.id);

describe('IntegrationsSection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists each integration with its host, never a header value', async () => {
    serve({ [LIST]: () => json([INTEGRATION]) });
    render(<IntegrationsSection />);

    expect(await screen.findByRole('heading', { name: 'crm' })).toBeInTheDocument();
    expect(screen.getByText('mcp.crm.example')).toBeInTheDocument();
    expect(screen.getByText('1 header: Authorization')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Let agents use crm' })).toBeChecked();
    expect(screen.queryByText(/Bearer/)).not.toBeInTheDocument();
  });

  it('adds an integration through the form', async () => {
    const user = userEvent.setup();
    const posted: unknown[] = [];
    serve({
      [LIST]: () => json([]),
      [`POST ${API.integrations}`]: (body) => {
        posted.push(body);
        return json(INTEGRATION, 201);
      },
    });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('button', { name: '+ Add an integration' }));
    await user.type(screen.getByLabelText('Name'), 'CRM');
    await user.type(screen.getByLabelText('Server URL'), INTEGRATION.url);
    await user.click(screen.getByRole('button', { name: '+ Add a header' }));
    await user.type(screen.getByLabelText('Header 1 name'), 'Authorization');
    await user.type(screen.getByLabelText('Header 1 value'), 'Bearer key-1234');
    expect(screen.getByLabelText('Header 1 value')).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: 'Connect' }));

    expect(posted).toEqual([
      {
        name: 'crm',
        url: INTEGRATION.url,
        headers: [{ name: 'Authorization', value: 'Bearer key-1234' }],
      },
    ]);
    expect(await screen.findByRole('heading', { name: 'crm' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('crm is connected.');
  });

  it('says what blocks saving before sending anything', async () => {
    const user = userEvent.setup();
    const fetchMock = serve({ [LIST]: () => json([]) });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('button', { name: '+ Add an integration' }));
    await user.click(screen.getByRole('button', { name: 'Connect' }));

    expect(screen.getByRole('alert')).toHaveTextContent(/The name needs 2 to 31 characters/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('tests a connection and shows the tools it found', async () => {
    const user = userEvent.setup();
    const tools = [{ name: 'crm_search', description: 'Find a contact.' }];
    serve({
      [LIST]: () => json([INTEGRATION]),
      [`POST ${API.testIntegration(INTEGRATION.id)}`]: () => json({ tools }),
    });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('button', { name: 'Test connection' }));

    expect(await screen.findByText('Connected. Found 1 tool:')).toBeInTheDocument();
    expect(screen.getByText('crm_search')).toBeInTheDocument();
    expect(screen.getByText(/1 tool found/)).toBeInTheDocument();
  });

  it('asks before deleting, and keeps the integration on "Keep it"', async () => {
    const user = userEvent.setup();
    serve({
      [LIST]: () => json([INTEGRATION]),
      [`DELETE ${ONE}`]: () => new Response(null, { status: 204 }),
    });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('button', { name: 'Delete' }));
    const confirm = screen.getByRole('group', { name: 'Delete crm?' });
    expect(within(confirm).getByRole('button', { name: 'Keep it' })).toHaveFocus();
    await user.click(within(confirm).getByRole('button', { name: 'Keep it' }));
    expect(screen.queryByRole('group', { name: 'Delete crm?' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: 'Delete' }));
    await user.click(screen.getByRole('button', { name: 'Delete crm' }));

    expect(await screen.findByText('No integrations yet.')).toBeInTheDocument();
  });

  it('turns an integration off', async () => {
    const user = userEvent.setup();
    serve({
      [LIST]: () => json([INTEGRATION]),
      [`PATCH ${ONE}`]: (body) => json({ ...INTEGRATION, ...(body as object) }),
    });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('switch', { name: 'Let agents use crm' }));

    expect(await screen.findByText(/crm is off/)).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Let agents use crm' })).not.toBeChecked();
  });

  it('edits an integration, showing saved values only as hints', async () => {
    const user = userEvent.setup();
    const patched: unknown[] = [];
    serve({
      [LIST]: () => json([INTEGRATION]),
      [`PATCH ${ONE}`]: (body) => {
        patched.push(body);
        return json({ ...INTEGRATION, ...(body as object) });
      },
    });
    render(<IntegrationsSection />);

    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const value = screen.getByLabelText('Header 1 value');
    expect(value).toHaveValue('');
    expect(value).toHaveAccessibleDescription(
      'Saved value ending in 1234. Leave it empty to keep it.',
    );
    await user.clear(screen.getByLabelText('Name'));
    await user.type(screen.getByLabelText('Name'), 'sales');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(patched).toEqual([{ name: 'sales' }]);
    expect(await screen.findByRole('heading', { name: 'sales' })).toBeInTheDocument();
  });
});
