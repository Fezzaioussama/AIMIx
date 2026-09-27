import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { App } from './App';
import { AuthProvider } from './core/auth/AuthContext';
import { clearTokens, saveTokens } from './core/auth/tokenStorage';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('App routing', () => {
  afterEach(() => clearTokens());

  it('shows the login screen on the login route', () => {
    renderAt('/login');
    expect(screen.getByRole('heading', { name: 'User Login' })).toBeInTheDocument();
  });

  it('redirects an unauthenticated visitor away from a protected route', () => {
    renderAt('/pipeline');
    expect(screen.getByRole('heading', { name: 'User Login' })).toBeInTheDocument();
  });

  it('renders the app nav for an authenticated visitor', () => {
    saveTokens({ access: 'token', refresh: 'refresh' });
    renderAt('/chat');
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pipelines' })).toBeInTheDocument();
  });
});
