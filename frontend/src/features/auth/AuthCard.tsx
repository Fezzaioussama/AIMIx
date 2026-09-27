import type { FormEvent, ReactNode } from 'react';

/**
 * Shared shell for the login and register cards — extracted rather than copied
 * into both screens (AGENTS.md §3, rule of two).
 */
interface AuthCardProps {
  title: string;
  submitLabel: string;
  isSubmitting: boolean;
  errorMessage: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
  footer: ReactNode;
}

export function AuthCard({
  title,
  submitLabel,
  isSubmitting,
  errorMessage,
  onSubmit,
  children,
  footer,
}: AuthCardProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f0f2f5] px-4">
      <div className="w-full max-w-md rounded-lg bg-white p-8 text-center shadow-md">
        <img src="/logo.png" alt="AIMIx" className="mx-auto mb-1 w-full max-w-[350px]" />
        <h2 className="mb-4 text-xl font-semibold text-[#333]">{title}</h2>
        <form onSubmit={onSubmit} noValidate>
          {children}
          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-4 w-full rounded bg-[#007bff] p-2.5 text-base text-white transition-colors hover:bg-[#0056b3] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Please wait…' : submitLabel}
          </button>
          {errorMessage && <p className="mt-4 text-sm text-red-600">{errorMessage}</p>}
          <div className="mt-4 text-sm text-[#555]">{footer}</div>
        </form>
      </div>
    </div>
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
    <div className="mb-4 text-left">
      <label htmlFor={id} className="mb-2 block font-bold text-[#555]">
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        required
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded border border-[#ccc] p-2.5 text-[#333] outline-none focus:border-[#007bff]"
      />
    </div>
  );
}
