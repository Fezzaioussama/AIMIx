import { useEffect, useState } from 'react';

import { countWaitingRuns } from '../../core/api/runs';

/** How often the number of runs waiting for you is fetched again (as the run list is). */
export const WAITING_RUNS_POLL_MS = 5000;

/**
 * How many of the signed-in user's runs wait for them to approve or decline an
 * action, fetched on mount and again every WAITING_RUNS_POLL_MS. It is 0 until
 * the first answer, and stays as it was when a fetch fails: a badge is not worth
 * an error message. Unmounting clears the timer and aborts the request in flight.
 */
export function useWaitingRuns(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const total = await countWaitingRuns(controller.signal);
        if (!controller.signal.aborted) setCount(total);
      } catch {
        // The count is only a hint; the next poll tries again.
      }
      if (!controller.signal.aborted) timer = setTimeout(() => void poll(), WAITING_RUNS_POLL_MS);
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  return count;
}
