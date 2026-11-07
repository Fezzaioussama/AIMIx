import type { Notice } from './useSubmission';

/**
 * What Settings → Integrations says when the browser comes back from an OAuth sign-in
 * (`?connected=<name>` or `?oauth_error=…`, put there by the server's call back), and
 * clears the query so a reload does not say it again. Null when it did not come back
 * from one.
 */
export function oauthReturnNotice(): Notice | null {
  const params = new URLSearchParams(window.location.search);
  const connected = params.get('connected');
  const error = params.get('oauth_error');
  if (connected === null && error === null) return null;
  window.history.replaceState(null, '', window.location.pathname);
  if (connected !== null) {
    return {
      kind: 'success',
      text: `${connected} is signed in: its tools can use your account there.`,
    };
  }
  return { kind: 'error', text: error || 'The sign-in did not go through.' };
}
