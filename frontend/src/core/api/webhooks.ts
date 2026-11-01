import { API } from './endpoints';
import { request } from './client';
import type { WebhookLink } from './webhookTypes';

/** One of the account's webhooks with its secret token; only its owner reads it. */
export function getWebhook(webhookId: number, signal?: AbortSignal): Promise<WebhookLink> {
  return request<WebhookLink>(API.webhook(webhookId), { signal });
}

/** The full address another app calls: this server's origin and the link's path. */
export function webhookUrl(token: string): string {
  return `${window.location.origin}${API.hook(token)}`;
}
