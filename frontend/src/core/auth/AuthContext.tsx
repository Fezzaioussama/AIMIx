import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import * as accountApi from '../api/account';
import * as authApi from '../api/auth';
import {
  clearTokens,
  endSession,
  hasSession,
  saveTokens,
  subscribeToSessionEnd,
} from './tokenStorage';

/**
 * Shared auth state (AGENTS.md §7 Observer): components read it through
 * useAuth() and never reach for the token or localStorage themselves.
 */
interface AuthContextValue {
  isAuthenticated: boolean;
  isReady: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Keeps this session signed in with the new tokens; every other one ends. */
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  /** Deletes the account and all its data, then ends the session. */
  deleteAccount: (password: string) => Promise<void>;
}

interface AuthProviderProps {
  children: ReactNode;
  /**
   * Forgets what this tab kept for an account (wired in main.tsx). It runs each time
   * the session ends (a logout, or the server refusing the session) and again on
   * signing in, so one account's data never reaches the next one in the tab.
   */
  forgetAccountData?: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Whether the screens are signed in. However the session ends, they sign out: the route
 * guard then sends the visitor to /login, while a public page (the landing page,
 * /login) stays where it is, so nothing loops.
 */
function useSignedIn(forgetAccountData?: () => void) {
  const [isAuthenticated, setIsAuthenticated] = useState(hasSession);
  useEffect(
    () =>
      subscribeToSessionEnd(() => {
        setIsAuthenticated(false);
        forgetAccountData?.();
      }),
    [forgetAccountData],
  );
  return [isAuthenticated, setIsAuthenticated] as const;
}

/**
 * A reload loses the in-memory access token, so the refresh cookie is tried once;
 * whether that answer is in yet.
 */
function useRestoredSession(setSignedIn: (signedIn: boolean) => void): boolean {
  const [isReady, setIsReady] = useState(hasSession);
  useEffect(() => {
    if (hasSession()) return;
    let active = true;
    void authApi
      .restoreSession()
      .then((tokens) => {
        saveTokens(tokens);
        if (active) setSignedIn(true);
      })
      .catch(() => clearTokens())
      .finally(() => {
        if (active) setIsReady(true);
      });
    return () => {
      active = false;
    };
  }, [setSignedIn]);
  return isReady;
}

export function AuthProvider({ children, forgetAccountData }: AuthProviderProps) {
  const [isAuthenticated, setIsAuthenticated] = useSignedIn(forgetAccountData);
  const isReady = useRestoredSession(setIsAuthenticated);

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await authApi.login(username, password);
      forgetAccountData?.(); // whatever the tab holds is from a session that ended
      saveTokens(tokens);
      setIsAuthenticated(true);
    },
    [forgetAccountData],
  );

  const register = useCallback(async (username: string, password: string) => {
    await authApi.register(username, password);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      endSession();
    }
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    saveTokens(await accountApi.changePassword(currentPassword, newPassword));
  }, []);

  const deleteAccount = useCallback(async (password: string) => {
    await accountApi.deleteAccount(password);
    endSession();
  }, []);

  const value = useMemo(
    () => ({ isAuthenticated, isReady, login, register, logout, changePassword, deleteAccount }),
    [isAuthenticated, isReady, login, register, logout, changePassword, deleteAccount],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
