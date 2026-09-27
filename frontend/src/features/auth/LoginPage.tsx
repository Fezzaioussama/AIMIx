import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AuthCard, AuthField } from './AuthCard';
import { useAuth } from '../../core/auth/AuthContext';

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
      navigate('/chat', { replace: true });
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
      title="User Login"
      submitLabel="Log In"
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onSubmit={handleSubmit}
      footer={
        <p className="m-0">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="text-[#007bff] underline">
            Create new account
          </Link>
        </p>
      }
    >
      <AuthField
        id="username"
        label="Username/Email:"
        type="text"
        value={username}
        onChange={setUsername}
      />
      <AuthField
        id="password"
        label="Password:"
        type="password"
        value={password}
        onChange={setPassword}
      />
    </AuthCard>
  );
}
