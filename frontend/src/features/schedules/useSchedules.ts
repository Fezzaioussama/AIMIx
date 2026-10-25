import { useCallback, useEffect, useState } from 'react';

import {
  deleteSchedule,
  listSchedules,
  runScheduleNow,
  updateSchedule,
} from '../../core/api/schedules';
import type { Run, Schedule, SchedulePatch } from '../../core/api/types';
import { errorText, useSubmission, type Submission } from '../settings/useSubmission';

/** The account's schedules, loaded once; a failure goes to the notice. */
function useScheduleList({ setNotice, setStatus }: Submission) {
  const [schedules, setSchedules] = useState<Schedule[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listSchedules(undefined, controller.signal)
      .then((loaded) => {
        if (!controller.signal.aborted) setSchedules(loaded);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setNotice({ kind: 'error', text: errorText(cause, 'Could not load your schedules.') });
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatus('idle');
      });
    return () => controller.abort();
  }, [setNotice, setStatus]);

  return [schedules, setSchedules] as const;
}

/**
 * State and transport for the Schedules list, kept out of the components (AGENTS.md §2):
 * the account's schedules, and switching one on or off, changing, deleting or starting it.
 * Each says how it went in `notice`.
 */
export function useSchedules() {
  const submission = useSubmission('loading');
  const { status, notice, setNotice, submit } = submission;
  const [schedules, setSchedules] = useScheduleList(submission);

  const replace = useCallback(
    (saved: Schedule) =>
      setSchedules((current) =>
        (current ?? []).map((item) => (item.id === saved.id ? saved : item)),
      ),
    [setSchedules],
  );

  const update = (schedule: Schedule, patch: SchedulePatch) =>
    submit(
      async () => replace(await updateSchedule(schedule.id, patch)),
      'Schedule saved.',
      'Could not save the schedule.',
    );

  const setEnabled = (schedule: Schedule, enabled: boolean) =>
    submit(
      async () => replace(await updateSchedule(schedule.id, { enabled })),
      enabled
        ? 'Schedule turned on.'
        : 'Schedule turned off. It will not run until you turn it on.',
      'Could not change the schedule.',
    );

  const remove = (schedule: Schedule) =>
    submit(
      async () => {
        await deleteSchedule(schedule.id);
        setSchedules((current) => (current ?? []).filter((item) => item.id !== schedule.id));
      },
      'Schedule deleted. The runs it started stay in your history.',
      'Could not delete the schedule.',
    );

  /** Start one of the schedule's runs now; the run, or null when it could not start. */
  const runNow = async (schedule: Schedule): Promise<Run | null> => {
    let started: Run | null = null;
    await submit(
      async () => {
        started = await runScheduleNow(schedule.id);
      },
      'Run started.',
      'Could not start the run.',
    );
    return started;
  };

  return {
    schedules,
    status,
    notice,
    actions: { update, setEnabled, remove, runNow, dismiss: () => setNotice(null) },
  };
}

export type SchedulesState = ReturnType<typeof useSchedules>;
