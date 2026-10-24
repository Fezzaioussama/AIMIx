import type { AuthTokens } from '../api/types';

/** Access tokens stay in memory. The rotating refresh token is an HttpOnly
 * cookie and is therefore never exposed to JavaScript or browser storage. */
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function saveTokens(tokens: AuthTokens): void {
  accessToken = tokens.access;
}

export function clearTokens(): void {
  accessToken = null;
}

export function hasSession(): boolean {
  return getAccessToken() !== null;
}
