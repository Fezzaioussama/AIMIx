/** A thrown value as words for the person: an `ApiError`'s message, else `fallback`. */
export function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error ? cause.message : fallback;
}
