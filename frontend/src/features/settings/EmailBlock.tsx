import { useState } from 'react';
import type { FormEvent } from 'react';

import { ToggleSwitch } from '../../core/ui/ToggleSwitch';
import { Block, FIELD, Outcome, PasswordField } from './AccountFields';
import { actionButtonClass } from './actionButton';
import type { useAccount } from './useAccount';

const NO_ADDRESS =
  'No address yet. Without one you cannot reset a forgotten password, and nothing can tell you when a run ends.';
const NOTIFICATIONS = 'Email me when a run ends, waits for me, or a schedule cannot start.';

/**
 * Settings → Account: the address password-reset links and notifications go to, and
 * the notifications switch. The password is asked again to change the address, since
 * it is where a reset link would go.
 */
export function EmailBlock({ account }: { account: ReturnType<typeof useAccount> }) {
  const { details } = account;
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const busy = account.email.status !== 'idle';

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await account.updateEmail(email.trim(), password)) {
      setEmail('');
      setPassword('');
    }
  }

  async function remove() {
    if (await account.updateEmail(null, password)) setPassword('');
  }

  return (
    <Block title="Email">
      <p className="mb-3 text-sm text-slate-300">
        {details?.email ? (
          <>
            Your address is <strong className="text-slate-100">{details.email}</strong>. A
            password-reset link and notifications go there.
          </>
        ) : (
          NO_ADDRESS
        )}
      </p>
      <form onSubmit={(event) => void handleSubmit(event)} noValidate className="space-y-3">
        <div>
          <label htmlFor="account-email" className="mb-1 block text-sm font-medium text-slate-300">
            {details?.email ? 'New address' : 'Email address'}
          </label>
          <input
            id="account-email"
            type="email"
            value={email}
            autoComplete="email"
            onChange={(event) => setEmail(event.target.value)}
            className={FIELD}
          />
        </div>
        <PasswordField
          id="email-password"
          label="Your password, to confirm"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || !email.trim() || !password}
            className={actionButtonClass('accent')}
          >
            Save address
          </button>
          {details?.email && (
            <button
              type="button"
              disabled={busy || !password}
              onClick={() => void remove()}
              className={actionButtonClass('neutral')}
            >
              Remove address
            </button>
          )}
          <Outcome submission={account.email} />
        </div>
      </form>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
        <span className="text-sm text-slate-300">{NOTIFICATIONS}</span>
        <ToggleSwitch
          checked={details?.email_notifications ?? true}
          label="Email notifications"
          disabled={!details?.email || account.notifications.status !== 'idle'}
          onChange={(enabled) => void account.setNotifications(enabled)}
        />
      </div>
      <Outcome submission={account.notifications} />
    </Block>
  );
}
