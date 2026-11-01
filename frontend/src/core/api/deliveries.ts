import { API } from './endpoints';
import { request } from './client';
import type { Delivery } from './deliveryTypes';

/** The account's result deliveries, oldest first: each address's host and hint only. */
export function listDeliveries(): Promise<Delivery[]> {
  return request<Delivery[]>(API.deliveries);
}

export function getDelivery(deliveryId: number, signal?: AbortSignal): Promise<Delivery> {
  return request<Delivery>(API.delivery(deliveryId), { signal });
}

/** Posts a first message to the address; once it is accepted, results go there. */
export function confirmDelivery(deliveryId: number): Promise<Delivery> {
  return request<Delivery>(API.confirmDelivery(deliveryId), { method: 'POST' });
}

/** Stop sending a workflow's results, or send them again (once confirmed). */
export function setDeliveryEnabled(deliveryId: number, enabled: boolean): Promise<Delivery> {
  return request<Delivery>(API.delivery(deliveryId), { method: 'PATCH', body: { enabled } });
}

export function deleteDelivery(deliveryId: number): Promise<void> {
  return request<void>(API.delivery(deliveryId), { method: 'DELETE' });
}
