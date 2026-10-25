import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { errorMessage } from '../../core/api/errorMessage';
import { cancelRun, getRun, resumeRun } from '../../core/api/runs';
import type { Run, RunBudget } from '../../core/api/types';
import { isActive } from './runStatus';

/** How often a queued or running run is fetched again. */
export const RUN_POLL_INTERVAL_MS = 1500;

export interface LiveRunState {
  /** The run as last fetched; null until the first answer. */
  run: Run | null;
  /** Why the last fetch, stop or resume failed; empty when it did not. */
  error: string;
  /** A stop or resume is in flight. */
  busy: boolean;
  stop: () => Promise<void>;
  /** Continue a stopped run, under new spending limits when given. */
  resume: (budget?: RunBudget) => Promise<void>;
  /** Show a run already in hand (one just started) without waiting for a fetch. */
  adopt: (run: Run) => void;
}

interface Failure {
  runId: number;
  message: string;
}

/**
 * Follows one run: fetches it, polls it every RUN_POLL_INTERVAL_MS while it is
 * queued or running, and stops polling once it ends. Unmounting (or switching
 * runs) clears the timer and aborts the request in flight. Stop and resume act
 * on it; a resumed run is polled again.
 */
export function useRun(runId: number | null): LiveRunState {
  const [run, setRun] = useState<Run | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const current = run !== null && run.id === runId ? run : null;
  const polling = runId !== null && (current === null || isActive(current.status));
  // A run in hand is fresh, so the first fetch can wait one interval. Read when
  // polling starts only: it must not restart the polling itself.
  const fresh = current !== null;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!polling || runId === null) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const next = await getRun(runId, controller.signal);
        setRun(next);
        setFailure(null);
        if (isActive(next.status)) timer = setTimeout(() => void poll(), RUN_POLL_INTERVAL_MS);
      } catch (cause) {
        if (controller.signal.aborted) return;
        setFailure({ runId, message: errorMessage(cause, 'Could not load this run.') });
        // A deleted run will not come back; anything else may be a passing hiccup.
        const gone = cause instanceof ApiError && cause.status === 404;
        if (!gone) timer = setTimeout(() => void poll(), RUN_POLL_INTERVAL_MS);
      }
    };
    if (fresh) timer = setTimeout(() => void poll(), RUN_POLL_INTERVAL_MS);
    else void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId, polling]);

  const act = useCallback(
    async (action: (id: number) => Promise<Run>, fallback: string) => {
      if (runId === null) return;
      setBusy(true);
      setFailure(null);
      try {
        const next = await action(runId);
        if (mounted.current) setRun(next);
      } catch (cause) {
        if (mounted.current) setFailure({ runId, message: errorMessage(cause, fallback) });
      } finally {
        if (mounted.current) setBusy(false);
      }
    },
    [runId],
  );

  const stop = useCallback(() => act(cancelRun, 'Could not stop this run.'), [act]);
  const resume = useCallback(
    (budget?: RunBudget) => act((id) => resumeRun(id, budget), 'Could not resume this run.'),
    [act],
  );
  const adopt = useCallback((next: Run) => setRun(next), []);
  const error = failure !== null && failure.runId === runId ? failure.message : '';

  return { run: current, error, busy, stop, resume, adopt };
}
