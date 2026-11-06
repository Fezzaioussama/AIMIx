import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ForgotPasswordPage } from './ForgotPasswordPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/forgot-password']}>
      <ForgotPasswordPage />
    </MemoryRouter>,
  );
}

function serve(response: () => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input) === '/api/password-reset') return response();
    return new Response('', { status: 404 });
  });
}

describe('ForgotPasswordPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('asks the server for a link and says an email may be on its way', async () => {
    const fetchMock = serve(() => new Response(null, { status: 204 }));
    renderPage();

    await userEvent.type(screen.getByLabelText('Email address'), ' Alice@example.com ');
    await userEvent.click(screen.getByRole('button', { name: 'Send the link' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      /an email with a link is on its way/,
    );
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({ email: 'Alice@example.com' });
    expect(screen.getByRole('button', { name: 'Send it again' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Log in' })).toHaveAttribute('href', '/login');
  });

  it('shows why when the server cannot send email', async () => {
    serve(() =>
      Response.json(
        { error: 'email_not_configured', detail: 'This server cannot send email.' },
        { status: 503 },
      ),
    );
    renderPage();

    await userEvent.type(screen.getByLabelText('Email address'), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send the link' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('This server cannot send email.'),
    );
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
