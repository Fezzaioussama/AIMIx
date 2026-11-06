import { useState } from 'react';
import type { FormEvent } from 'react';

import { PASSWORD_RULE } from '../../core/auth/passwordRule';
import { Block, Outcome, PasswordField } from './AccountFields';
import { actionButtonClass } from './actionButton';
import { EmailBlock } from './EmailBlock';
import { useAccount } from './useAccount';

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

/** Settings → Account: the email address, the password, a copy of everything the account holds, deletion. */
export function AccountSection() {
  const account = useAccount();

  return (
    <section aria-labelledby="account-heading" className="mt-8">
      <h2 id="account-heading" className="text-2xl font-bold tracking-tight">
        Account
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        Your email address, your password, a copy of your data, and closing your account.
      </p>
      <div className="space-y-4">
        <EmailBlock account={account} />
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
