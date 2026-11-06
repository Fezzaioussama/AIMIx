import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ResetPasswordPage } from './ResetPasswordPage';

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ResetPasswordPage />
    </MemoryRouter>,
  );
}

function serve(response: () => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === '/api/password-reset/confirm') return response();
    return new Response('', { status: 404 });
  });
}

async function typePasswords(first: string, second: string) {
  await userEvent.type(screen.getByLabelText('New password'), first);
  await userEvent.type(screen.getByLabelText('New password, again'), second);
  await userEvent.click(screen.getByRole('button', { name: 'Change password' }));
}

describe('ResetPasswordPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the token and the new password, then offers to sign in', async () => {
    const fetchMock = serve(() => new Response(null, { status: 204 }));
    renderPage('/reset-password?token=abc.def');

    await typePasswords('a-brand-new-pass-1', 'a-brand-new-pass-1');

    expect(await screen.findByRole('status')).toHaveTextContent('Your password was changed.');
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({
      token: 'abc.def',
      password: 'a-brand-new-pass-1',
    });
    expect(screen.queryByRole('button', { name: 'Change password' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'sign in' })).toHaveAttribute('href', '/login');
  });

  it('asks nothing of the server while the two passwords differ', async () => {
    const fetchMock = serve(() => new Response(null, { status: 204 }));
    renderPage('/reset-password?token=abc');

    await typePasswords('a-brand-new-pass-1', 'another-pass-2');

    expect(await screen.findByRole('alert')).toHaveTextContent('The two passwords differ.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows the reason when the link is refused', async () => {
    serve(() =>
      Response.json(
        { error: 'validation_error', detail: 'token: This link is not valid any more.' },
        { status: 400 },
      ),
    );
    renderPage('/reset-password?token=old');

    await typePasswords('a-brand-new-pass-1', 'a-brand-new-pass-1');

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('This link is not valid any more.'),
    );
  });

  it('says so, and where to get a new link, when the token is missing', () => {
    serve(() => new Response(null, { status: 204 }));
    renderPage('/reset-password');

    expect(screen.getByRole('alert')).toHaveTextContent('This link is incomplete.');
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Ask for a new one' })).toHaveAttribute(
      'href',
      '/forgot-password',
    );
  });
});
