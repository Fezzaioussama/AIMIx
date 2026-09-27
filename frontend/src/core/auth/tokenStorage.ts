import type { AuthTokens } from '../api/types';

/**
 * The only module in the app allowed to touch localStorage (AGENTS.md §2:
 * components must never read it directly). Every access is guarded because
 * storage throws in private mode and is absent during tests/SSR.
 */
const ACCESS_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage unavailable — the session simply does not survive a reload.
  }
}

export function getAccessToken(): string | null {
  return read(ACCESS_KEY);
}

export function saveTokens(tokens: AuthTokens): void {
  write(ACCESS_KEY, tokens.access);
  write(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  } catch {
    // Nothing to clear.
  }
}

export function hasSession(): boolean {
  return getAccessToken() !== null;
}
