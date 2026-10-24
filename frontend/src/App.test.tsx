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

  it('serves the public landing page at the root, without a session', async () => {
    renderAt('/');
    expect(
      await screen.findByRole('heading', { level: 1, name: /multi-agent workflows/i }),
    ).toBeInTheDocument();
  });

  it('shows the login screen on the login route', () => {
    renderAt('/login');
    expect(screen.getByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('redirects an unauthenticated visitor away from a protected route', async () => {
    renderAt('/pipeline');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('renders the app nav for an authenticated visitor', () => {
    saveTokens({ access: 'token' });
    renderAt('/chat');
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pipelines' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  });

  it('keeps Pipelines current on the auto-pipeline screen', () => {
    saveTokens({ access: 'token' });
    renderAt('/auto-pipeline');
    expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Chat' })).not.toHaveAttribute('aria-current');
  });
});
