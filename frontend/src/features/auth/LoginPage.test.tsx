import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens } from '../../core/auth/tokenStorage';
import { HOME_PATH } from '../../core/routes';
import { LoginPage } from './LoginPage';

function Landed() {
  return <p>Landed on {useLocation().pathname}</p>;
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Landed />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('lands on the mission workspace after signing in', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
      String(input) === '/api/login'
        ? Response.json({ access: 'token' })
        : new Response('', { status: 401 }),
    );
    renderLogin();

    await userEvent.type(screen.getByLabelText('Username or email'), 'alice');
    await userEvent.type(screen.getByLabelText('Password'), 'a-strong-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));

    expect(await screen.findByText(`Landed on ${HOME_PATH}`)).toBeInTheDocument();
    expect(HOME_PATH).toBe('/mission');
  });

  it('stays on the sign-in screen, with the reason, when the sign-in fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
      String(input) === '/api/login'
        ? Response.json(
            { error: 'invalid_credentials', detail: 'Wrong username or password.' },
            { status: 401 },
          )
        : new Response('', { status: 401 }),
    );
    renderLogin();

    await userEvent.type(screen.getByLabelText('Username or email'), 'alice');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Wrong username or password.'),
    );
    expect(screen.queryByText(/Landed on/)).not.toBeInTheDocument();
  });
});
