/** Auth payloads, re-exported from `types.ts`. */

export interface AuthTokens {
  access: string;
}

/** GET /api/protected: the signed-in account, by id and by name. */
export interface WhoAmI {
  message: string;
  user_id: number;
  username: string;
}
