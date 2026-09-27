import { API } from './endpoints';
import { request } from './client';
import type { AuthTokens } from './types';

export function login(username: string, password: string): Promise<AuthTokens> {
  return request<AuthTokens>(API.login, { method: 'POST', body: { username, password } });
}

export function register(username: string, password: string): Promise<unknown> {
  return request<unknown>(API.register, { method: 'POST', body: { username, password } });
}
