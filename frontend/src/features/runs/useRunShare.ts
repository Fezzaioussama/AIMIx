import { useCallback, useEffect, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { getRunShare, shareRun, unshareRun } from '../../core/api/runs';
import type { RunShare } from '../../core/api/types';
import { useMountedRef } from '../../core/hooks/useMountedRef';

export interface RunShareState {
  /** The run's link; null while it is not shared, undefined until the first answer. */
  link: RunShare | null | undefined;
  /** A share or a withdrawal is in flight. */
  busy: boolean;
  /** Why the last one failed; empty when it did not. */
  error: string;
  share: () => Promise<void>;
  unshare: () => Promise<void>;
}

/**
 * A run's share link: read when the run opens (so it survives leaving the page), made
 * and withdrawn from its report. Switching runs aborts the read in flight.
 */
export function useRunShare(runId: number): RunShareState {
  const [link, setLink] = useState<RunShare | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useMountedRef();

  useEffect(() => {
    const controller = new AbortController();
    setLink(undefined);
    getRunShare(runId, controller.signal)
      .then((found) => {
        if (!controller.signal.aborted) setLink(found);
      })
      .catch(() => {
        // No link to show is not worth a message: Share still works.
        if (!controller.signal.aborted) setLink(null);
      });
    return () => controller.abort();
  }, [runId]);

  const act = useCallback(
    async (action: () => Promise<RunShare | null>, fallback: string) => {
      setBusy(true);
      setError('');
      try {
        const next = await action();
        if (mounted.current) setLink(next);
      } catch (cause) {
        if (mounted.current) setError(errorMessage(cause, fallback));
      } finally {
        if (mounted.current) setBusy(false);
      }
    },
    [mounted],
  );

  const share = useCallback(
    () => act(() => shareRun(runId), 'Could not make the link.'),
    [act, runId],
  );
  const unshare = useCallback(
    () =>
      act(async () => {
        await unshareRun(runId);
        return null;
      }, 'Could not withdraw the link.'),
    [act, runId],
  );

  return { link, busy, error, share, unshare };
}
