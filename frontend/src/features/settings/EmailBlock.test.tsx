import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Account } from '../../core/api/types';
import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens, saveTokens } from '../../core/auth/tokenStorage';
import { AccountSection } from './AccountSection';
import { json } from './testData';

const ACCOUNT: Account = {
  username: 'alice',
  email: null,
  email_notifications: true,
  created_at: '2026-10-24T10:00:00Z',
};

interface Call {
  path: string;
  method: string;
  body: unknown;
}

/** Answers the account routes from `account`, applying what is sent, and records the calls. */
function serve(account: Account, refuse?: Response): Call[] {
  const calls: Call[] = [];
  let current = account;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = String(input);
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ path, method: init?.method ?? 'GET', body });
    if (refuse && path !== API.account) return refuse.clone();
    if (path === API.accountEmail) current = { ...current, email: body.email };
    else if (path === API.accountNotifications)
      current = { ...current, email_notifications: body.email_notifications };
    else if (path !== API.account) return json({ error: 'not_found', detail: 'Not found.' }, 404);
    return json(current);
  });
  return calls;
}

function renderSection() {
  render(
    <MemoryRouter initialEntries={['/settings/account']}>
      <AuthProvider>
        <Routes>
          <Route path="/settings/account" element={<AccountSection />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('EmailBlock', () => {
  beforeEach(() => saveTokens({ access: 'token' }));
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('saves an address with the password, then shows it and lets notifications be switched', async () => {
    const calls = serve(ACCOUNT);
    renderSection();
    const user = userEvent.setup();
    expect(await screen.findByText(/No address yet/)).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Email notifications' })).toBeDisabled();

    await user.type(screen.getByLabelText('Email address'), 'alice@example.com');
    await user.type(screen.getByLabelText('Your password, to confirm'), 'the-password-123');
    await user.click(screen.getByRole('button', { name: 'Save address' }));

    expect(await screen.findByText('Address saved.')).toBeInTheDocument();
    expect(calls.find((call) => call.path === API.accountEmail)).toEqual({
      path: API.accountEmail,
      method: 'PUT',
      body: { email: 'alice@example.com', password: 'the-password-123' },
    });
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
    const toggle = screen.getByRole('switch', { name: 'Email notifications' });
    expect(toggle).toBeEnabled();
    await user.click(toggle);
    await waitFor(() =>
      expect(calls.at(-1)).toEqual({
        path: API.accountNotifications,
        method: 'PUT',
        body: { email_notifications: false },
      }),
    );
    expect(await screen.findByText('You will not be emailed.')).toBeInTheDocument();
  });

  it('removes the address with the password, and shows a refusal', async () => {
    serve({ ...ACCOUNT, email: 'alice@example.com' });
    renderSection();
    const user = userEvent.setup();
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Your password, to confirm'), 'the-password-123');
    await user.click(screen.getByRole('button', { name: 'Remove address' }));

    expect(await screen.findByText('Address removed.')).toBeInTheDocument();
    expect(screen.getByText(/No address yet/)).toBeInTheDocument();
  });

  it('says why when the address is refused', async () => {
    serve(
      ACCOUNT,
      json({ error: 'validation_error', detail: 'password: The password is not correct.' }, 400),
    );
    renderSection();
    const user = userEvent.setup();
    await screen.findByText(/No address yet/);

    await user.type(screen.getByLabelText('Email address'), 'alice@example.com');
    await user.type(screen.getByLabelText('Your password, to confirm'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Save address' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The password is not correct.');
  });
});
