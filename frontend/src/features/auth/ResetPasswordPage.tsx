import { useState } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';

import { confirmPasswordReset } from '../../core/api/auth';
import { PASSWORD_RULE } from '../../core/auth/passwordRule';
import { AuthCard, AuthField } from './AuthCard';

const INCOMPLETE = 'This link is incomplete. Ask for a new one.';
const DONE = 'Your password was changed. Sign in with it.';

/**
 * /reset-password?token=…: the page a reset link opens. The token names the account; a
 * new password replaces the old one once, and the link stops working.
 */
export function ResetPasswordPage() {
  const token = useSearchParams()[0].get('token') ?? '';
  const [password, setPassword] = useState('');
  const [again, setAgain] = useState('');
  const [errorMessage, setErrorMessage] = useState(token ? '' : INCOMPLETE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage('');
    if (password !== again) {
      setErrorMessage('The two passwords differ.');
      return;
    }
    setIsSubmitting(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
    } catch (cause) {
      setErrorMessage(
        cause instanceof Error
          ? cause.message
          : 'Could not change the password. Ask for a new link.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const canSubmit = Boolean(token) && !done;
  return (
    <AuthCard
      title="Choose a new password"
      subtitle={done ? '' : PASSWORD_RULE}
      submitLabel={canSubmit ? 'Change password' : undefined}
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onSubmit={handleSubmit}
      footer={
        token
          ? { prompt: 'Back to', to: '/login', label: 'sign in' }
          : { prompt: 'Lost the link?', to: '/forgot-password', label: 'Ask for a new one' }
      }
    >
      {done && (
        <p
          role="status"
          className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200"
        >
          {DONE}
        </p>
      )}
      {canSubmit && (
        <>
          <AuthField
            id="password"
            label="New password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
          />
          <AuthField
            id="confirmPassword"
            label="New password, again"
            type="password"
            value={again}
            onChange={setAgain}
            autoComplete="new-password"
          />
        </>
      )}
    </AuthCard>
  );
}
