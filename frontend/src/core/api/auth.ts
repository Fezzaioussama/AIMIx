import { API } from './endpoints';
import { refreshAccessToken, request } from './client';
import type { AuthTokens, WhoAmI } from './types';

export function login(username: string, password: string): Promise<AuthTokens> {
  return request<AuthTokens>(API.login, { method: 'POST', body: { username, password } });
}

/** Creates the account; an email address is optional (password resets, notifications). */
export function register(username: string, password: string, email?: string): Promise<unknown> {
  const body = email ? { username, password, email } : { username, password };
  return request<unknown>(API.register, { method: 'POST', body });
}

/** Emails a reset link to the account using this address, if any; the server says nothing either way. */
export function requestPasswordReset(email: string): Promise<void> {
  return request<void>(API.requestPasswordReset, { method: 'POST', body: { email } });
}

/** Sets a new password with the token of a reset link; the link then stops working. */
export function confirmPasswordReset(token: string, password: string): Promise<void> {
  return request<void>(API.confirmPasswordReset, { method: 'POST', body: { token, password } });
}

export function restoreSession(): Promise<AuthTokens> {
  return refreshAccessToken();
}

export function logout(): Promise<void> {
  return request<void>(API.logout, { method: 'POST' });
}

/** Whose session this is; also confirms the access token is still valid. */
export function whoAmI(signal?: AbortSignal): Promise<WhoAmI> {
  return request<WhoAmI>(API.whoAmI, { signal });
}
