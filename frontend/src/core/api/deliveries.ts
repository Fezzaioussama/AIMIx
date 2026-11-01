import { API } from './endpoints';
import { request } from './client';
import type { Delivery } from './deliveryTypes';

export function getDelivery(deliveryId: number, signal?: AbortSignal): Promise<Delivery> {
  return request<Delivery>(API.delivery(deliveryId), { signal });
}

/** Posts a first message to the address; once it is accepted, results go there. */
export function confirmDelivery(deliveryId: number): Promise<Delivery> {
  return request<Delivery>(API.confirmDelivery(deliveryId), { method: 'POST' });
}

export function deleteDelivery(deliveryId: number): Promise<void> {
  return request<void>(API.delivery(deliveryId), { method: 'DELETE' });
}
