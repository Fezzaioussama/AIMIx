import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { hasSession } from './tokenStorage';

/**
 * Route guard — AGENTS.md §6 "auth-protected by default". Every feature route
 * sits behind this; only /login and /register are public, deliberately.
 */
export function RequireAuth() {
  const location = useLocation();

  // Read storage directly rather than context state: a full page reload must
  // resolve the session before the first render, with no redirect flash.
  if (!hasSession()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
