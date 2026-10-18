import { AnimatePresence, motion } from 'motion/react';
import type { FormEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { GlowButton } from '../../core/ui/GlowButton';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { BlurText } from '../../core/ui/reactbits/BlurText';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { AuthLayout } from './AuthLayout';

/**
 * Shared shell for the login and register cards — extracted rather than copied
 * into both screens (AGENTS.md §3, rule of two).
 */
interface AuthCardProps {
  title: string;
  subtitle: string;
  submitLabel: string;
  isSubmitting: boolean;
  errorMessage: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
  /** "Don't have an account? Create one" — the link to the other screen. */
  footer: { prompt: string; to: string; label: string };
}

export function AuthCard({
  title,
  subtitle,
  submitLabel,
  isSubmitting,
  errorMessage,
  onSubmit,
  children,
  footer,
}: AuthCardProps) {
  return (
    <AuthLayout>
      <AnimatedContent distance={30} scale={0.97} delay={0.1} className="w-full max-w-md">
        <SpotlightCard variant="glass" className="p-8 sm:p-10">
          <img src="/logo.png" alt="AIMIx" className="mx-auto mb-6 h-20 w-auto lg:hidden" />
          <h2 className="text-3xl font-bold tracking-tight text-white">
            <BlurText text={title} />
          </h2>
          <p className="mt-2 mb-8 text-sm text-slate-400">{subtitle}</p>
          <form onSubmit={onSubmit} noValidate>
            {children}
            <GlowButton type="submit" block busy={isSubmitting} className="mt-6">
              {isSubmitting ? 'Please wait…' : submitLabel}
            </GlowButton>
            <AuthError message={errorMessage} />
            <AuthFooter {...footer} />
          </form>
        </SpotlightCard>
      </AnimatedContent>
    </AuthLayout>
  );
}

function AuthError({ message }: { message: string }) {
  return (
    <AnimatePresence>
      {message && (
        <motion.p
          role="alert"
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="mt-4 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300"
        >
          {message}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

function AuthFooter({ prompt, to, label }: AuthCardProps['footer']) {
  return (
    <p className="mt-6 text-center text-sm text-slate-400">
      {prompt}{' '}
      <Link to={to} className="font-medium text-sky-400 transition-colors hover:text-sky-300">
        {label}
      </Link>
    </p>
  );
}

interface AuthFieldProps {
  id: string;
  label: string;
  type: 'text' | 'password';
  value: string;
  onChange: (value: string) => void;
}

export function AuthField({ id, label, type, value, onChange }: AuthFieldProps) {
  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-300">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        required
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-slate-100 transition-[border-color,box-shadow] outline-none placeholder:text-slate-500 focus:border-sky-400/60 focus:shadow-[0_0_0_4px_rgba(56,189,248,0.12)]"
      />
    </div>
  );
}
