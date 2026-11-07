import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { IntegrationOAuth } from '../../core/api/types';
import { IntegrationCard } from './IntegrationCard';
import { oauthReturnNotice } from './oauthReturn';
import { INTEGRATION } from './testData';

function renderCard(oauth: IntegrationOAuth) {
  const signIn = vi.fn();
  const signOut = vi.fn();
  render(
    <IntegrationCard
      integration={{ ...INTEGRATION, oauth }}
      busy={false}
      onToggle={vi.fn()}
      onToggleApproval={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onTest={vi.fn()}
      onSignIn={signIn}
      onSignOut={signOut}
    />,
  );
  return { signIn, signOut };
}

describe('OAuth sign-in on an integration card', () => {
  it('offers the sign-in while there is none', async () => {
    const { signIn } = renderCard('');

    expect(screen.getByText('Not signed in: only its headers are sent.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in with OAuth' }));

    expect(signIn).toHaveBeenCalledOnce();
  });

  it('says when it is done, and signs out or starts again', async () => {
    const { signIn, signOut } = renderCard('connected');

    expect(screen.getByText(/Signed in with OAuth/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await userEvent.click(screen.getByRole('button', { name: 'Sign in again' }));

    expect(signOut).toHaveBeenCalledOnce();
    expect(signIn).toHaveBeenCalledOnce();
  });

  it('says when a sign-in was started but not finished', () => {
    renderCard('pending');

    expect(screen.getByText(/Sign-in started/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in again' })).toBeInTheDocument();
  });
});

describe('oauthReturnNotice', () => {
  afterEach(() => window.history.replaceState(null, '', '/'));

  it('reads how the sign-in went from the URL the server sent the browser to, once', () => {
    window.history.replaceState(null, '', '/settings/integrations?connected=crm');

    expect(oauthReturnNotice()).toEqual({
      kind: 'success',
      text: 'crm is signed in: its tools can use your account there.',
    });
    expect(window.location.search).toBe('');
    expect(oauthReturnNotice()).toBeNull();
  });

  it('shows the error the server put there', () => {
    window.history.replaceState(null, '', '/settings?oauth_error=The+sign-in+took+too+long.');

    expect(oauthReturnNotice()).toEqual({ kind: 'error', text: 'The sign-in took too long.' });
  });
});
