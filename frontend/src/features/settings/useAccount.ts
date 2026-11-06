import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  downloadAccountExport,
  getAccount,
  setEmail,
  setEmailNotifications,
} from '../../core/api/account';
import type { Account } from '../../core/api/types';
import { useAuth } from '../../core/auth/AuthContext';
import { saveBlob } from '../../core/saveBlob';
import { useSubmission } from './useSubmission';

/** The day's date, for the saved file's name: aimix-account-2026-10-31.json. */
function exportFileName(): string {
  return `aimix-account-${new Date().toISOString().slice(0, 10)}.json`;
}

/**
 * Settings → Account: the account's details (its address and notification switch),
 * change the address or the switch, change the password, save a copy of everything
 * the account holds, delete it. Each action has its own busy flag and outcome line.
 */
export function useAccount() {
  const { changePassword, deleteAccount } = useAuth();
  const navigate = useNavigate();
  const [details, setDetails] = useState<Account | null>(null);
  const email = useSubmission('idle');
  const notifications = useSubmission('idle');
  const password = useSubmission('idle');
  const copy = useSubmission('idle');
  const removal = useSubmission('idle');

  useEffect(() => {
    const controller = new AbortController();
    getAccount(controller.signal)
      .then((account) => {
        if (!controller.signal.aborted) setDetails(account);
      })
      .catch(() => {
        // The forms still work without the details; a refusal shows on submit.
      });
    return () => controller.abort();
  }, []);

  const updateEmail = useCallback(
    (address: string | null, currentPassword: string) =>
      email.submit(
        async () => setDetails(await setEmail(address, currentPassword)),
        address ? 'Address saved.' : 'Address removed.',
        'Could not save the address.',
      ),
    [email.submit],
  );

  const setNotifications = useCallback(
    (enabled: boolean) =>
      notifications.submit(
        async () => setDetails(await setEmailNotifications(enabled)),
        enabled ? 'You will be emailed about your runs.' : 'You will not be emailed.',
        'Could not change the setting.',
      ),
    [notifications.submit],
  );

  const updatePassword = useCallback(
    (current: string, next: string) =>
      password.submit(
        () => changePassword(current, next),
        'Password changed. Your other devices were signed out.',
        'Could not change the password.',
      ),
    [password.submit, changePassword],
  );

  const downloadCopy = useCallback(
    () =>
      copy.submit(
        async () => saveBlob(await downloadAccountExport(), exportFileName()),
        'Your data was downloaded.',
        'Could not download your data.',
      ),
    [copy.submit],
  );

  const removeAccount = useCallback(
    async (confirmPassword: string) => {
      const done = await removal.submit(
        () => deleteAccount(confirmPassword),
        'Your account was deleted.',
        'Could not delete the account.',
      );
      if (done) navigate('/', { replace: true });
    },
    [removal.submit, deleteAccount, navigate],
  );

  return {
    details,
    email,
    notifications,
    password,
    copy,
    removal,
    updateEmail,
    setNotifications,
    updatePassword,
    downloadCopy,
    removeAccount,
  };
}
