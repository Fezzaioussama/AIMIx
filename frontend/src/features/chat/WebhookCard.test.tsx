import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../core/api/client';
import { getWebhook } from '../../core/api/webhooks';
import type { WebhookLink } from '../../core/api/webhookTypes';
import { WebhookCard } from './WebhookCard';

vi.mock('../../core/api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/api/webhooks')>()),
  getWebhook: vi.fn(),
}));

const LINK: WebhookLink = {
  id: 3,
  pipeline_id: 9,
  pipeline_name: 'News digest',
  enabled: true,
  last_called_at: null,
  last_error: null,
  token: 'secret-token-123',
};

beforeEach(() => {
  vi.mocked(getWebhook).mockReset();
});

describe('WebhookCard', () => {
  it('reads the link from the server and copies it', async () => {
    vi.mocked(getWebhook).mockResolvedValue(LINK);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    render(<WebhookCard webhookId={3} />);

    const url = `${window.location.origin}/api/hooks/secret-token-123`;
    expect(await screen.findByText(url)).toBeInTheDocument();
    expect(screen.getByText('News digest')).toBeInTheDocument();
    expect(screen.getByText('On')).toBeInTheDocument();
    expect(vi.mocked(getWebhook).mock.calls[0]?.[0]).toBe(3);

    await userEvent.click(screen.getByRole('button', { name: /Copy link/ }));
    expect(writeText).toHaveBeenCalledWith(url);
    expect(await screen.findByRole('button', { name: /Copied/ })).toBeInTheDocument();
  });

  it('says so when the link cannot be read', async () => {
    vi.mocked(getWebhook).mockImplementation(() =>
      Promise.reject(new ApiError('Webhook 3 was not found.', 404)),
    );
    render(<WebhookCard webhookId={3} />);

    expect(await screen.findByText('Webhook 3 was not found.')).toBeInTheDocument();
  });
});
