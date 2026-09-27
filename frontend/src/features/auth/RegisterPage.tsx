import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AuthCard, AuthField } from './AuthCard';
import { useAuth } from '../../core/auth/AuthContext';

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage('');

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    setIsSubmitting(true);
    try {
      await register(username, password);
      navigate('/login', { replace: true });
    } catch (cause) {
      setErrorMessage(
        cause instanceof Error ? cause.message : 'Registration failed. Please try again.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthCard
      title="Create Account"
      submitLabel="Register"
      isSubmitting={isSubmitting}
      errorMessage={errorMessage}
      onSubmit={handleSubmit}
      footer={
        <p className="m-0">
          Already have an account?{' '}
          <Link to="/login" className="text-[#007bff] underline">
            Log in here
          </Link>
        </p>
      }
    >
      <AuthField id="username" label="Username:" type="text" value={username} onChange={setUsername} />
      <AuthField
        id="password"
        label="Password:"
        type="password"
        value={password}
        onChange={setPassword}
      />
      <AuthField
        id="confirmPassword"
        label="Confirm Password:"
        type="password"
        value={confirmPassword}
        onChange={setConfirmPassword}
      />
    </AuthCard>
  );
}
