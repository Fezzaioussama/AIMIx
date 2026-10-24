import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import * as authApi from '../api/auth';
import { clearTokens, hasSession, saveTokens } from './tokenStorage';

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
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(hasSession);
  const [isReady, setIsReady] = useState(hasSession);

  useEffect(() => {
    if (hasSession()) return;
    let active = true;
    void authApi
      .restoreSession()
      .then((tokens) => {
        saveTokens(tokens);
        if (active) setIsAuthenticated(true);
      })
      .catch(() => clearTokens())
      .finally(() => {
        if (active) setIsReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await authApi.login(username, password);
    saveTokens(tokens);
    setIsAuthenticated(true);
  }, []);

  const register = useCallback(async (username: string, password: string) => {
    await authApi.register(username, password);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearTokens();
      setIsAuthenticated(false);
    }
  }, []);

  const value = useMemo(
    () => ({ isAuthenticated, isReady, login, register, logout }),
    [isAuthenticated, isReady, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  return context;
}
