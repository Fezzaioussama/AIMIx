import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { downloadAccountExport } from '../../core/api/account';
import { useAuth } from '../../core/auth/AuthContext';
import { saveBlob } from '../../core/saveBlob';
import { useSubmission } from './useSubmission';

/** The day's date, for the saved file's name: aimix-account-2026-10-31.json. */
function exportFileName(): string {
  return `aimix-account-${new Date().toISOString().slice(0, 10)}.json`;
}

/**
 * Settings → Account: change the password, save a copy of everything the account
 * holds, delete it. Each action has its own busy flag and outcome line.
 */
export function useAccount() {
  const { changePassword, deleteAccount } = useAuth();
  const navigate = useNavigate();
  const password = useSubmission('idle');
  const copy = useSubmission('idle');
  const removal = useSubmission('idle');

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

  return { password, copy, removal, updatePassword, downloadCopy, removeAccount };
}
