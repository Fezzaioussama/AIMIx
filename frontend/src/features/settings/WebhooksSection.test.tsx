import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { DELIVERY, WEBHOOK, json } from './testData';
import { WebhooksSection } from './WebhooksSection';

type Handler = (body: unknown) => Response;

/** Answers `"<METHOD> <path>"` requests and records their bodies; anything else is a 404. */
function serve(handlers: Record<string, Handler>) {
  const sent: Array<[string, unknown]> = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    sent.push([key, body]);
    const handler = handlers[key];
    return handler ? handler(body) : json({ error: 'not_found', detail: 'Not found.' }, 404);
  });
  return sent;
}

const LISTS = {
  [`GET ${API.webhooks}`]: () => json([WEBHOOK]),
  [`GET ${API.deliveries}`]: () => json([DELIVERY]),
};

function renderSection() {
  return render(
    <MemoryRouter>
      <WebhooksSection />
    </MemoryRouter>,
  );
}

describe('WebhooksSection', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists the webhooks and deliveries, never a link or a whole address', async () => {
    serve(LISTS);
    renderSection();

    expect(await screen.findByRole('heading', { name: 'Weekly digest' })).toBeInTheDocument();
    expect(screen.getByText(/Last called .*: a run started\./)).toBeInTheDocument();
    expect(
      screen.getByRole('switch', { name: 'Let other apps start Weekly digest' }),
    ).toBeChecked();
    expect(screen.getByRole('heading', { name: 'Sales report' })).toBeInTheDocument();
    expect(screen.getByText('hooks.slack.com …XyZ9')).toBeInTheDocument();
    expect(screen.getByText(/Waiting for your OK/)).toBeInTheDocument();
    expect(screen.queryByText(/\/api\/hooks\//)).not.toBeInTheDocument();
  });

  it('says what to ask the chat while a list is empty', async () => {
    serve({ [`GET ${API.webhooks}`]: () => json([]), [`GET ${API.deliveries}`]: () => json([]) });
    renderSection();

    const hints = await screen.findAllByText(/None yet/);
    expect(hints).toHaveLength(2);
    expect(within(hints[0]).getByRole('link', { name: 'Chat' })).toHaveAttribute('href', '/chat');
  });

  it('switches a webhook off and says what that means', async () => {
    const user = userEvent.setup();
    const sent = serve({
      ...LISTS,
      [`PATCH ${API.webhook(WEBHOOK.id)}`]: () => json({ ...WEBHOOK, enabled: false }),
    });
    renderSection();

    await user.click(await screen.findByRole('switch', { name: /Let other apps start/ }));

    expect(sent).toContainEqual([`PATCH ${API.webhook(WEBHOOK.id)}`, { enabled: false }]);
    expect(
      await screen.findByText("Weekly digest's link is off: calling it starts nothing."),
    ).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Let other apps start/ })).not.toBeChecked();
  });

  it('reads the link only when asked, and the new one after a renewal', async () => {
    const user = userEvent.setup();
    let token = 'first-token';
    serve({
      ...LISTS,
      [`GET ${API.webhook(WEBHOOK.id)}`]: () => json({ ...WEBHOOK, token }),
      [`POST ${API.renewWebhook(WEBHOOK.id)}`]: () => {
        token = 'second-token';
        return json(WEBHOOK);
      },
    });
    renderSection();

    await user.click(await screen.findByRole('button', { name: 'Show link' }));
    expect(await screen.findByText(/\/api\/hooks\/first-token$/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'New link' }));
    const question = screen.getByRole('group', { name: 'Give Weekly digest a new link?' });
    await user.click(within(question).getByRole('button', { name: 'Get a new link' }));

    expect(await screen.findByText(/\/api\/hooks\/second-token$/)).toBeInTheDocument();
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
  });

  it('asks before deleting a link, and keeping it puts the focus back', async () => {
    const user = userEvent.setup();
    serve({
      ...LISTS,
      [`DELETE ${API.webhook(WEBHOOK.id)}`]: () => new Response(null, { status: 204 }),
    });
    renderSection();

    const remove = await screen.findByRole('button', { name: 'Delete' });
    await user.click(remove);
    await user.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(screen.queryByRole('group')).not.toBeInTheDocument();
    expect(remove).toHaveFocus();

    await user.click(remove);
    await user.click(screen.getByRole('button', { name: 'Delete the link' }));

    expect(await screen.findByText("Weekly digest's link is deleted.")).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Weekly digest' })).not.toBeInTheDocument();
    expect(screen.getAllByText(/None yet/)).toHaveLength(1);
  });

  it('confirms a delivery waiting for the OK, which then gets its switch', async () => {
    const user = userEvent.setup();
    serve({
      ...LISTS,
      [`POST ${API.confirmDelivery(DELIVERY.id)}`]: () => json({ ...DELIVERY, confirmed: true }),
    });
    renderSection();

    expect(await screen.findByRole('heading', { name: 'Sales report' })).toBeInTheDocument();
    expect(screen.queryByRole('switch', { name: /Sales report/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(await screen.findByText("Sales report's results now go to Slack.")).toBeInTheDocument();
    expect(
      screen.getByRole('switch', { name: "Send Sales report's results to Slack" }),
    ).toBeChecked();
  });

  it('says why a change failed, in the server’s words', async () => {
    const user = userEvent.setup();
    serve({
      ...LISTS,
      [`PATCH ${API.webhook(WEBHOOK.id)}`]: () =>
        json({ error: 'not_found', detail: 'Webhook not found.' }, 404),
    });
    renderSection();

    await user.click(await screen.findByRole('switch', { name: /Let other apps start/ }));

    expect(await screen.findByText('Webhook not found.')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: /Let other apps start/ })).toBeChecked();
  });
});
