import { useState } from 'react';
import type { FormEvent } from 'react';

import { requestPasswordReset } from '../../core/api/auth';
import { AuthCard, AuthField } from './AuthCard';

const SENT =
  'If an account uses this address, an email with a link is on its way. Check your inbox, and the spam folder.';

/**
 * /forgot-password: the person gives the account's address and the server emails a reset
 * link, saying nothing about whether the address has an account.
 */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage('');
    setIsSubmitting(true);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (cause) {
      setErrorMessage(
        cause instanceof Error ? cause.message : 'Could not send the email. Please try again.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Forgot your password?"
      subtitle="Give the email address of your account, and we send you a link to choose a new one."
      submitLabel={sent ? 'Send it again' : 'Send the link'}
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onSubmit={handleSubmit}
      footer={{ prompt: 'Remembered it?', to: '/login', label: 'Log in' }}
    >
      {sent && (
        <p
          role="status"
          className="mb-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200"
        >
          {SENT}
        </p>
      )}
      <AuthField
        id="email"
        label="Email address"
        type="email"
        value={email}
        onChange={setEmail}
        autoComplete="email"
      />
    </AuthCard>
  );
}
