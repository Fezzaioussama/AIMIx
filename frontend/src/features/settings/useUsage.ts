import { useEffect, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import type { UsageReport } from '../../core/api/types';
import { fetchUsage } from '../../core/api/usage';

/** How many days back the Settings page counts. */
export const USAGE_DAYS = 30;

/** The account's usage over the last `days` days, loaded once; leaving cancels the request. */
export function useUsage(days: number = USAGE_DAYS) {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetchUsage(days, controller.signal)
      .then((next) => {
        setReport(next);
        setError('');
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(cause, 'Could not load your usage.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [days]);

  return { report, error, loading };
}
