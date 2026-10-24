import { afterEach, describe, expect, it } from 'vitest';

import { clearTokens, getAccessToken, saveTokens } from './tokenStorage';

describe('token storage', () => {
  afterEach(clearTokens);

  it('keeps the access token in memory instead of browser storage', () => {
    saveTokens({ access: 'short-lived-access' });

    expect(getAccessToken()).toBe('short-lived-access');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
