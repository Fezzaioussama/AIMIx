import type { ReactNode } from 'react';

import { NoticeLine } from './NoticeLine';
import type { Submission } from './useSubmission';

/** The text field style the Account tab's forms share. */
export const FIELD =
  'w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

interface PasswordFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  hint?: string;
}

export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  hint,
}: PasswordFieldProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-300">
        {label}
      </label>
      <input
        id={id}
        type="password"
        value={value}
        autoComplete={autoComplete}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.value)}
        className={FIELD}
      />
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-400">
          {hint}
        </p>
      )}
    </div>
  );
}

/** One titled card of the Account tab. */
export function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
      <h3 className="mb-3 text-base font-semibold text-white">{title}</h3>
      {children}
    </div>
  );
}

/** What a submission said, once it ended. */
export function Outcome({ submission }: { submission: Submission }) {
  return submission.notice ? <NoticeLine notice={submission.notice} /> : null;
}
