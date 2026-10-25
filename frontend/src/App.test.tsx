import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';
import { AuthProvider } from './core/auth/AuthContext';
import { clearTokens, saveTokens } from './core/auth/tokenStorage';
import { COMMON_ROUTES, SAVED, routeFetch } from './features/mission/testData';

// The pipeline sub-navigation counts waiting runs with a request of its own; these
// routing tests hand out one canned response per screen.
vi.mock('./features/runs/useWaitingRuns', () => ({ useWaitingRuns: () => 0 }));

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
    // The landing page is a lazy chunk with the 3D scene behind it: loading it takes
    // longer than the default second when the whole suite runs at once, or on a slow CI box.
    expect(
      await screen.findByRole(
        'heading',
        { level: 1, name: /multi-agent workflows/i },
        { timeout: 8000 },
      ),
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

  it('lists Missions first in the app nav, then the rest, all reachable by name', () => {
    saveTokens({ access: 'token' });
    renderAt('/chat');
    const bar = screen.getAllByRole('link').filter((link) => link.closest('nav'));
    expect(bar.map((link) => link.textContent)).toEqual([
      'Missions',
      'Chat',
      'Pipelines',
      'Files',
      'Settings',
    ]);
    expect(screen.getByRole('link', { name: 'Missions' })).toHaveAttribute('href', '/mission');
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument();
  });

  it('serves the mission workspace as the front door, with Missions current', async () => {
    saveTokens({ access: 'token' });
    routeFetch(COMMON_ROUTES);
    renderAt('/mission');
    expect(screen.getByRole('link', { name: 'Missions' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Chat' })).not.toHaveAttribute('aria-current');
    expect(await screen.findByRole('heading', { level: 1, name: 'Missions' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'What do you want to get done?' }),
    ).toBeInTheDocument();
  });

  it('keeps Missions current on a saved mission’s address', async () => {
    saveTokens({ access: 'token' });
    routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED });
    renderAt('/mission/7');
    expect(screen.getByRole('link', { name: 'Missions' })).toHaveAttribute('aria-current', 'page');
    const log = await screen.findByRole('log', { name: 'Conversation with AIMIx' });
    expect(await within(log).findByText(/Here’s your “Competitor brief” team/)).toBeInTheDocument();
  });

  it('keeps the mission workspace behind sign-in', async () => {
    renderAt('/mission');
    expect(await screen.findByRole('heading', { name: 'Welcome back' })).toBeInTheDocument();
  });

  it('renders the app nav for an authenticated visitor', () => {
    saveTokens({ access: 'token' });
    renderAt('/chat');
    expect(screen.getByRole('link', { name: 'Chat' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pipelines' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Files' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
  });

  it('serves the Files screen behind the nav item of the same name', async () => {
    saveTokens({ access: 'token' });
    const empty = { files: [], used_bytes: 0, quota_bytes: 1, max_file_bytes: 1 };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...empty, allowed_extensions: ['.pdf'] }), { status: 200 }),
    );
    renderAt('/files');

    expect(screen.getByRole('link', { name: 'Files' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('heading', { level: 1, name: 'Files' })).toBeInTheDocument();
    expect(await screen.findByText('No files yet')).toBeInTheDocument();
  });

  it('keeps Pipelines current on the auto-pipeline screen', async () => {
    saveTokens({ access: 'token' });
    renderAt('/auto-pipeline');
    expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Chat' })).not.toHaveAttribute('aria-current');
    expect(await screen.findByRole('link', { name: 'Start from a template' })).toHaveAttribute(
      'href',
      '/templates',
    );
  });

  it('serves the template gallery as a pipeline screen', async () => {
    const gallery = vi.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json([]));
    saveTokens({ access: 'token' });
    renderAt('/templates');
    expect(await screen.findByRole('group', { name: 'Filter by category' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Start from a template' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Templates' })).toHaveAttribute('aria-current', 'page');
    gallery.mockRestore();
  });

  it('serves a run deep link under Pipelines, with the Runs tab current', async () => {
    saveTokens({ access: 'token' });
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => new Promise<Response>(() => {}));
    renderAt('/runs/7');
    expect(screen.getByRole('link', { name: 'Pipelines' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('link', { name: 'Runs' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});
