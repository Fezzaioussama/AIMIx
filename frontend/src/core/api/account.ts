import { API } from './endpoints';
import { request, requestBlob, UPLOAD_TIMEOUT_MS } from './client';
import type { AuthTokens } from './types';

/**
 * Replaces the password. Every other session of the account ends; this one goes on
 * with the token pair returned (the refresh token comes back as its HttpOnly cookie).
 */
export function changePassword(currentPassword: string, newPassword: string): Promise<AuthTokens> {
  return request<AuthTokens>(API.changePassword, {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

/**
 * Everything the account holds, as a JSON file to save (GDPR access and portability).
 * A large account takes a while to gather, so it gets the file-transfer timeout.
 */
export function downloadAccountExport(signal?: AbortSignal): Promise<Blob> {
  return requestBlob(API.exportAccount, { timeoutMs: UPLOAD_TIMEOUT_MS, signal });
}

/** Deletes the account with all its data; the password is asked again. Cannot be undone. */
export function deleteAccount(password: string): Promise<void> {
  return request<void>(API.deleteAccount, { method: 'POST', body: { password } });
}
