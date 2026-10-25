import type { AuthTokens } from '../api/types';

/** Access tokens stay in memory. The rotating refresh token is an HttpOnly
 * cookie and is therefore never exposed to JavaScript or browser storage. */
let accessToken: string | null = null;

/** Who hears that the session ended (Observer); AuthProvider is the subscriber. */
const sessionEndListeners = new Set<() => void>();

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

/**
 * Ends the session in this tab and says so: on logout, and when the server refuses
 * the session (its refresh cookie was turned down). Clearing the token alone would
 * leave the screens signed in, with every call failing.
 */
export function endSession(): void {
  clearTokens();
  for (const listener of [...sessionEndListeners]) listener();
}

/** Calls `listener` each time the session ends; returns the unsubscribe. */
export function subscribeToSessionEnd(listener: () => void): () => void {
  sessionEndListeners.add(listener);
  return () => {
    sessionEndListeners.delete(listener);
  };
}
