import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';

import { actionButtonClass } from './actionButton';
import { NoticeLine } from './NoticeLine';
import { useAccount } from './useAccount';
import type { Submission } from './useSubmission';

/** Shown under the new password; the server's rule is the one that holds. */
const PASSWORD_RULE = 'At least 12 characters, not a common password, not your username.';

const FIELD =
  'w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

interface PasswordFieldProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: 'current-password' | 'new-password';
  hint?: string;
}

function PasswordField({ id, label, value, onChange, autoComplete, hint }: PasswordFieldProps) {
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

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
      <h3 className="mb-3 text-base font-semibold text-white">{title}</h3>
      {children}
    </div>
  );
}

function Outcome({ submission }: { submission: Submission }) {
  return submission.notice ? <NoticeLine notice={submission.notice} /> : null;
}

function PasswordForm({ account }: { account: ReturnType<typeof useAccount> }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const mismatch = again !== '' && next !== again;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await account.updatePassword(current, next)) {
      setCurrent('');
      setNext('');
      setAgain('');
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} noValidate className="space-y-3">
      <PasswordField
        id="current-password"
        label="Current password"
        value={current}
        onChange={setCurrent}
        autoComplete="current-password"
      />
      <PasswordField
        id="new-password"
        label="New password"
        value={next}
        onChange={setNext}
        autoComplete="new-password"
        hint={PASSWORD_RULE}
      />
      <PasswordField
        id="new-password-again"
        label="New password, again"
        value={again}
        onChange={setAgain}
        autoComplete="new-password"
        hint={mismatch ? 'The two new passwords differ.' : undefined}
      />
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={account.password.status !== 'idle' || !current || !next || next !== again}
          className={actionButtonClass('accent')}
        >
          Change password
        </button>
        <Outcome submission={account.password} />
      </div>
    </form>
  );
}

function DeleteForm({ account }: { account: ReturnType<typeof useAccount> }) {
  const [password, setPassword] = useState('');
  const [understood, setUnderstood] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void account.removeAccount(password);
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-3">
      <p className="text-sm text-slate-300">
        Deletes your pipelines, runs, schedules, integrations, saved keys and files for good. Stop
        any active run first. Download your data before, if you want to keep it.
      </p>
      <PasswordField
        id="delete-password"
        label="Your password"
        value={password}
        onChange={setPassword}
        autoComplete="current-password"
      />
      <label className="flex items-start gap-2 text-sm text-slate-300">
        <input
          type="checkbox"
          checked={understood}
          onChange={(event) => setUnderstood(event.target.checked)}
          className="mt-0.5"
        />
        I understand that this cannot be undone.
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={account.removal.status !== 'idle' || !password || !understood}
          className={actionButtonClass('danger')}
        >
          Delete my account
        </button>
        <Outcome submission={account.removal} />
      </div>
    </form>
  );
}

/** Settings → Account: the password, a copy of everything the account holds, deletion. */
export function AccountSection() {
  const account = useAccount();

  return (
    <section aria-labelledby="account-heading" className="mt-12 border-t border-white/10 pt-10">
      <h2 id="account-heading" className="text-2xl font-bold tracking-tight">
        Account
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        Your password, a copy of your data, and closing your account.
      </p>
      <div className="space-y-4">
        <Block title="Password">
          <PasswordForm account={account} />
        </Block>
        <Block title="Your data">
          <p className="mb-3 text-sm text-slate-300">
            Everything your account holds — pipelines, runs with their inputs and outputs,
            schedules, integrations and the list of your files — as one JSON file. Saved keys and
            header values stay secret: only their last characters are in it.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={account.copy.status !== 'idle'}
              onClick={() => void account.downloadCopy()}
              className={actionButtonClass('neutral')}
            >
              Download my data
            </button>
            <Outcome submission={account.copy} />
          </div>
        </Block>
        <Block title="Delete account">
          <DeleteForm account={account} />
        </Block>
      </div>
    </section>
  );
}
