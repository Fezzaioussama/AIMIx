import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens } from '../../core/auth/tokenStorage';
import { HOME_PATH } from '../../core/routes';
import { RegisterPage } from './RegisterPage';

function Landed() {
  return <p>Landed on {useLocation().pathname}</p>;
}

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <AuthProvider>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="*" element={<Landed />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

/** Answers each API path from `answers`; anything else (the session restore) is a 401. */
function serve(answers: Record<string, Response>) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(
      async (input) => answers[String(input)]?.clone() ?? new Response('', { status: 401 }),
    );
}

async function fillAndSubmit(confirm = 'a-strong-pass-1') {
  await userEvent.type(screen.getByLabelText('Username'), 'alice');
  await userEvent.type(screen.getByLabelText('Password', { exact: true }), 'a-strong-pass-1');
  await userEvent.type(screen.getByLabelText('Confirm password'), confirm);
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
}

describe('RegisterPage', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('creates the account and signs the person in, landing on the mission workspace', async () => {
    const fetchMock = serve({
      '/api/register': Response.json({ username: 'alice' }, { status: 201 }),
      '/api/login': Response.json({ access: 'token' }),
    });
    renderRegister();

    await fillAndSubmit();

    expect(await screen.findByText(`Landed on ${HOME_PATH}`)).toBeInTheDocument();
    const paths = fetchMock.mock.calls.map(([input]) => String(input));
    expect(paths.indexOf('/api/register')).toBeLessThan(paths.indexOf('/api/login'));
  });

  it('stays on the form, with the reason, when the account is refused', async () => {
    serve({
      '/api/register': Response.json(
        { error: 'registration_closed', detail: 'Registration is closed.' },
        { status: 403 },
      ),
    });
    renderRegister();

    await fillAndSubmit();

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Registration is closed.'),
    );
    expect(screen.queryByText(/Landed on/)).not.toBeInTheDocument();
  });

  it('sends the person to sign in by hand when only the automatic sign-in fails', async () => {
    serve({
      '/api/register': Response.json({ username: 'alice' }, { status: 201 }),
      '/api/login': Response.json(
        { error: 'rate_limited', detail: 'Too many attempts.' },
        { status: 429 },
      ),
    });
    renderRegister();

    await fillAndSubmit();

    expect(await screen.findByText('Landed on /login')).toBeInTheDocument();
  });

  it('says, before the account is created, which terms and policy apply', () => {
    serve({});
    renderRegister();

    expect(screen.getByRole('link', { name: 'terms of use' })).toHaveAttribute('href', '/terms');
    expect(screen.getByRole('link', { name: 'privacy policy' })).toHaveAttribute(
      'href',
      '/privacy',
    );
    const legal = screen.getByRole('navigation', { name: 'Legal' });
    expect(within(legal).getByRole('link', { name: 'Legal notice' })).toHaveAttribute(
      'href',
      '/legal',
    );
  });

  it('does not ask the server anything when the two passwords differ', async () => {
    const fetchMock = serve({});
    renderRegister();
    fetchMock.mockClear();

    await fillAndSubmit('another-pass-2');

    expect(await screen.findByRole('alert')).toHaveTextContent('Passwords do not match.');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
