import { API } from './endpoints';
import { request, requestBlob, UPLOAD_TIMEOUT_MS } from './client';
import type { Account, AuthTokens } from './types';

/** The account as the Settings page shows it: name, email address, notifications. */
export function getAccount(signal?: AbortSignal): Promise<Account> {
  return request<Account>(API.account, { signal });
}

/** The address reset links and notifications go to (null removes it); the password is asked again. */
export function setEmail(email: string | null, password: string): Promise<Account> {
  return request<Account>(API.accountEmail, { method: 'PUT', body: { email, password } });
}

/** Whether the account is emailed when a run ends, waits for it, or a schedule cannot start. */
export function setEmailNotifications(enabled: boolean): Promise<Account> {
  return request<Account>(API.accountNotifications, {
    method: 'PUT',
    body: { email_notifications: enabled },
  });
}

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
