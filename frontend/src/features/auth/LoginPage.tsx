import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { AuthCard, AuthField } from './AuthCard';
import { useAuth } from '../../core/auth/AuthContext';
import { HOME_PATH } from '../../core/routes';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage('');
    setIsSubmitting(true);
    try {
      await login(username, password);
      navigate(HOME_PATH, { replace: true });
    } catch (cause) {
      setErrorMessage(
        cause instanceof Error
          ? cause.message
          : 'Login failed. Please check your username and password.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Sign in to continue to your AIMIx workspace."
      submitLabel="Log in"
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onSubmit={handleSubmit}
      footer={{ prompt: 'Don’t have an account?', to: '/register', label: 'Create one' }}
    >
      <AuthField
        id="username"
        label="Username or email"
        type="text"
        value={username}
        onChange={setUsername}
      />
      <AuthField
        id="password"
        label="Password"
        type="password"
        value={password}
        onChange={setPassword}
      />
    </AuthCard>
  );
}
