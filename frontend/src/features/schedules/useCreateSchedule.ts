import { useCallback, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { createSchedule } from '../../core/api/schedules';
import type { PipelineInput, Schedule } from '../../core/api/types';
import { useCancellableRequest } from '../../core/hooks/useCancellableRequest';
import { toCreate, type ScheduleDraft } from './scheduleDraft';

/**
 * Create a schedule of a saved pipeline from the form's draft: `busy` while it is saved,
 * then the schedule that was `created`, or the `error` the server gave. Leaving the screen
 * drops the request, so nothing updates afterwards (AGENTS.md §8).
 */
export function useCreateSchedule(pipelineId: number | undefined, inputs: PipelineInput[]) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [created, setCreated] = useState<Schedule | null>(null);
  const { start, finish } = useCancellableRequest();

  const create = useCallback(
    async (draft: ScheduleDraft) => {
      if (pipelineId === undefined) return;
      const controller = start();
      setBusy(true);
      setError('');
      setCreated(null);
      let saved: Schedule | null = null;
      let failure = '';
      try {
        saved = await createSchedule(toCreate(pipelineId, inputs, draft), controller.signal);
      } catch (cause) {
        failure = errorMessage(cause, 'Could not save the schedule.');
      }
      // Not the current request any more (a newer one, or the screen left): stay silent.
      if (!finish(controller)) return;
      setBusy(false);
      setCreated(saved);
      setError(failure);
    },
    [pipelineId, inputs, start, finish],
  );

  return { busy, error, created, create };
}
