import { API } from './endpoints';
import { request } from './client';
import type { Webhook, WebhookLink } from './webhookTypes';

/** The account's webhooks, oldest first, without their links. */
export function listWebhooks(): Promise<Webhook[]> {
  return request<Webhook[]>(API.webhooks);
}

/** One of the account's webhooks with its secret token; only its owner reads it. */
export function getWebhook(webhookId: number, signal?: AbortSignal): Promise<WebhookLink> {
  return request<WebhookLink>(API.webhook(webhookId), { signal });
}

/** Off, its link answers like an unknown one and starts nothing; on, it works again. */
export function setWebhookEnabled(webhookId: number, enabled: boolean): Promise<Webhook> {
  return request<Webhook>(API.webhook(webhookId), { method: 'PATCH', body: { enabled } });
}

/** A new link; the old one stops working at once. */
export function renewWebhook(webhookId: number): Promise<Webhook> {
  return request<Webhook>(API.renewWebhook(webhookId), { method: 'POST' });
}

export function deleteWebhook(webhookId: number): Promise<void> {
  return request<void>(API.webhook(webhookId), { method: 'DELETE' });
}

/** The full address another app calls: this server's origin and the link's path. */
export function webhookUrl(token: string): string {
  return `${window.location.origin}${API.hook(token)}`;
}
