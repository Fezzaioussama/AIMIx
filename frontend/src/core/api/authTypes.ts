/** Auth payloads, re-exported from `types.ts`. */

export interface AuthTokens {
  access: string;
}

/** GET /api/account: the account as the Settings page shows it. */
export interface Account {
  username: string;
  /** Where password-reset links and notifications go; null until given. */
  email: string | null;
  /** Whether the account is emailed when a run ends, waits for it, or a schedule cannot start. */
  email_notifications: boolean;
  created_at: string;
}

/** GET /api/protected: the signed-in account, by id and by name. */
export interface WhoAmI {
  message: string;
  user_id: number;
  username: string;
}
