import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { AuthProvider } from '../../core/auth/AuthContext';
import { clearTokens, getAccessToken, hasSession, saveTokens } from '../../core/auth/tokenStorage';
import { AccountSection } from './AccountSection';
import { json } from './testData';

const saveBlob = vi.hoisted(() => vi.fn());
vi.mock('../../core/saveBlob', () => ({ saveBlob }));

interface Call {
  path: string;
  method: string;
  body: unknown;
}

/** Answers each account route with `answers[path]`, recording what was sent. */
function serve(answers: Record<string, Response>): Call[] {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = typeof input === 'string' ? input : input instanceof URL ? input.pathname : '';
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ path, method: init?.method ?? 'GET', body });
    return answers[path]?.clone() ?? json({ error: 'not_found', detail: 'Not found.' }, 404);
  });
  return calls;
}

function renderSection() {
  render(
    <MemoryRouter initialEntries={['/settings']}>
      <AuthProvider>
        <Routes>
          <Route path="/settings" element={<AccountSection />} />
          <Route path="/" element={<h1>Landing</h1>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('AccountSection', () => {
  beforeEach(() => saveTokens({ access: 'old-token' }));
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
    saveBlob.mockReset();
  });

  it('changes the password and keeps the session on the new token', async () => {
    const calls = serve({ [API.changePassword]: json({ access: 'new-token' }) });
    renderSection();
    const user = userEvent.setup();
    const submit = screen.getByRole('button', { name: 'Change password' });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText('Current password'), 'old-password-123');
    await user.type(screen.getByLabelText('New password'), 'new-password-456');
    await user.type(screen.getByLabelText('New password, again'), 'new-password-456');
    await user.click(submit);

    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
    expect(calls[0]).toEqual({
      path: API.changePassword,
      method: 'POST',
      body: { current_password: 'old-password-123', new_password: 'new-password-456' },
    });
    expect(getAccessToken()).toBe('new-token');
    expect(screen.getByLabelText('Current password')).toHaveValue('');
  });

  it('keeps the button off while the two new passwords differ', async () => {
    serve({});
    renderSection();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Current password'), 'old-password-123');
    await user.type(screen.getByLabelText('New password'), 'new-password-456');
    await user.type(screen.getByLabelText('New password, again'), 'new-password-457');

    expect(screen.getByText('The two new passwords differ.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change password' })).toBeDisabled();
  });

  it("shows the server's reason and stays signed in when the password is refused", async () => {
    const refusal = {
      error: 'validation_error',
      detail: 'current_password: The password is not correct.',
    };
    serve({ [API.changePassword]: json(refusal, 400) });
    renderSection();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Current password'), 'wrong-password-1');
    await user.type(screen.getByLabelText('New password'), 'new-password-456');
    await user.type(screen.getByLabelText('New password, again'), 'new-password-456');
    await user.click(screen.getByRole('button', { name: 'Change password' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The password is not correct.');
    expect(hasSession()).toBe(true);
  });

  it('saves a copy of the account as a JSON file', async () => {
    serve({ [API.exportAccount]: json({ account: { username: 'tester' } }) });
    renderSection();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Download my data' }));

    expect(await screen.findByText('Your data was downloaded.')).toBeInTheDocument();
    expect(saveBlob).toHaveBeenCalledWith(
      expect.any(Blob),
      expect.stringMatching(/^aimix-account-\d{4}-\d{2}-\d{2}\.json$/),
    );
  });

  it('deletes the account only once confirmed, then signs out to the landing page', async () => {
    const calls = serve({ [API.deleteAccount]: new Response(null, { status: 204 }) });
    renderSection();
    const user = userEvent.setup();
    const remove = screen.getByRole('button', { name: 'Delete my account' });

    await user.type(screen.getByLabelText('Your password'), 'my-password-123');
    expect(remove).toBeDisabled();
    await user.click(screen.getByLabelText('I understand that this cannot be undone.'));
    await user.click(remove);

    expect(await screen.findByRole('heading', { name: 'Landing' })).toBeInTheDocument();
    expect(calls.at(-1)).toEqual({
      path: API.deleteAccount,
      method: 'POST',
      body: { password: 'my-password-123' },
    });
    await waitFor(() => expect(hasSession()).toBe(false));
  });

  it('stays signed in when the deletion is refused', async () => {
    const busy = {
      error: 'conflict',
      detail: 'Stop your active runs before deleting your account.',
    };
    serve({ [API.deleteAccount]: json(busy, 409) });
    renderSection();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText('Your password'), 'my-password-123');
    await user.click(screen.getByLabelText('I understand that this cannot be undone.'));
    await user.click(screen.getByRole('button', { name: 'Delete my account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Stop your active runs');
    expect(hasSession()).toBe(true);
  });
});
