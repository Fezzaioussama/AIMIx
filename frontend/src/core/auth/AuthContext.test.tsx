import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { request } from '../api/client';
import { API } from '../api/endpoints';
import {
  forgetAllMissions,
  missionKey,
  readMission,
  writeMission,
} from '../../features/mission/missionStorage';
import { you } from '../../features/mission/missionMessages';
import { AuthProvider, useAuth } from './AuthContext';
import { RequireAuth } from './RequireAuth';
import { clearTokens, hasSession, saveTokens } from './tokenStorage';

const REFUSED = { error: 'not_authenticated', detail: 'Token expired' };

/** A protected screen that loads something, with a way out. */
function Workspace() {
  const { logout } = useAuth();
  useEffect(() => {
    request(API.pipelines).catch(() => undefined);
  }, []);
  return (
    <>
      <h1>Workspace</h1>
      <button type="button" onClick={() => logout().catch(() => undefined)}>
        Log out
      </button>
    </>
  );
}

function SignIn() {
  const { login } = useAuth();
  return (
    <>
      <h1>Sign in</h1>
      <button type="button" onClick={() => void login('bob', 'pass')}>
        Log in
      </button>
    </>
  );
}

function renderAt(path: string, forgetAccountData = vi.fn()) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider forgetAccountData={forgetAccountData}>
        <Routes>
          <Route path="/" element={<h1>Landing</h1>} />
          <Route path="/login" element={<SignIn />} />
          <Route element={<RequireAuth />}>
            <Route path="/workspace" element={<Workspace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
  return forgetAccountData;
}

/** Answers each `/api/...` path; anything unlisted is refused as unauthenticated. */
function serve(routes: Record<string, () => Response>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const answer = routes[String(input)];
    return answer ? answer() : Response.json(REFUSED, { status: 401 });
  });
}

describe('AuthProvider', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('sends the visitor to sign in when the server refuses the session mid-visit', async () => {
    saveTokens({ access: 'stale' });
    serve({});
    const forget = renderAt('/workspace');

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(forget).toHaveBeenCalled();
    expect(hasSession()).toBe(false);
  });

  it('signs out and forgets the account’s data on logout', async () => {
    saveTokens({ access: 'token' });
    serve({
      [API.pipelines]: () => Response.json([]),
      [API.logout]: () => new Response(null, { status: 204 }),
    });
    const forget = renderAt('/workspace');

    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(forget).toHaveBeenCalledOnce();
  });

  it('signs out even when the server cannot be told about the logout', async () => {
    saveTokens({ access: 'token' });
    serve({
      [API.pipelines]: () => Response.json([]),
      [API.logout]: () => Response.json({ error: 'error', detail: 'Down' }, { status: 503 }),
    });
    const forget = renderAt('/workspace');

    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(forget).toHaveBeenCalledOnce();
  });

  it('leaves a visitor on a public page when no session can be restored', async () => {
    const fetchMock = serve({});
    const forget = renderAt('/');

    await waitFor(() => expect(forget).toHaveBeenCalled());
    expect(screen.getByRole('heading', { name: 'Landing' })).toBeInTheDocument();
    // One refresh attempt, then nothing more: no loop of redirects or retries.
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('stays on the sign-in screen when no session can be restored there', async () => {
    const fetchMock = serve({});
    const forget = renderAt('/login');

    await waitFor(() => expect(forget).toHaveBeenCalled());
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('forgets what the tab still holds when someone signs in', async () => {
    serve({ [API.login]: () => Response.json({ access: 'token' }) });
    const forget = renderAt('/login');
    await waitFor(() => expect(forget).toHaveBeenCalled());
    forget.mockClear();

    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));

    await waitFor(() => expect(hasSession()).toBe(true));
    expect(forget).toHaveBeenCalledOnce();
  });

  it('leaves no mission draft for the next account once wired to the mission storage', async () => {
    saveTokens({ access: 'token' });
    writeMission(missionKey(), { messages: [you('Compare my competitors')], draft: null });
    writeMission(missionKey(7), { messages: [you('Make it shorter')], draft: null });
    serve({
      [API.pipelines]: () => Response.json([]),
      [API.logout]: () => new Response(null, { status: 204 }),
    });
    renderAt('/workspace', vi.fn(forgetAllMissions));

    await userEvent.click(await screen.findByRole('button', { name: 'Log out' }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(readMission(missionKey()).messages).toEqual([]);
    expect(readMission(missionKey(7)).messages).toEqual([]);
  });
});
