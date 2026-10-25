import { useEffect, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { previewSchedule } from '../../core/api/schedules';
import type { ScheduleTiming } from '../../core/api/types';

/** How long a timing must stay as it is before the server is asked when it would run. */
export const PREVIEW_DELAY_MS = 300;

interface Answer {
  /** The timing it answers, so an answer for an earlier one is never shown. */
  key: string;
  nextRunAt: string | null;
  error: string;
}

/**
 * When a schedule with this timing would first run, as the server works it out (daylight
 * saving and month ends included — nothing is worked out here). Asks once the timing has
 * stayed put for `PREVIEW_DELAY_MS`, and drops a request a newer timing makes obsolete or
 * the screen leaving. `null` means the timing is not complete: nothing is asked.
 */
export function useSchedulePreview(timing: ScheduleTiming | null) {
  const key = timing === null ? '' : JSON.stringify(timing);
  const [answer, setAnswer] = useState<Answer | null>(null);

  useEffect(() => {
    if (timing === null) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      // An answer that arrives after its request was dropped must not replace a newer one.
      previewSchedule(timing, controller.signal)
        .then((preview) => {
          if (!controller.signal.aborted) {
            setAnswer({ key, nextRunAt: preview.next_run_at, error: '' });
          }
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          const error = errorMessage(cause, 'Could not work out the next run.');
          setAnswer({ key, nextRunAt: null, error });
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `key` stands for `timing`: a new object holding the same fields is not a change.
  }, [key]);

  const current = answer !== null && answer.key === key ? answer : null;
  return {
    nextRunAt: current?.nextRunAt ?? null,
    error: current?.error ?? '',
    /** A timing is waiting for its answer. */
    loading: timing !== null && current === null,
  };
}
