import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { BusyNotice } from '../ui/BusyNotice';
import { useAuth } from './AuthContext';

/**
 * Route guard — AGENTS.md §6 "auth-protected by default". Every feature route
 * sits behind this; only the landing page (/) and /login and /register are
 * public, deliberately.
 */
export function RequireAuth() {
  const location = useLocation();
  const { isAuthenticated, isReady } = useAuth();

  if (!isReady) {
    return <BusyNotice className="min-h-screen justify-center">Restoring session…</BusyNotice>;
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
