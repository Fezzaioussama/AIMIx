import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

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
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

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

  it('serves a run deep link under Pipelines, with the Runs tab current', () => {
    saveTokens({ access: 'token' });
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>(() => {}));
    renderAt('/runs/7');
    expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page');
  });
});
