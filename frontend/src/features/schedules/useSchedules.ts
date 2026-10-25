import { useCallback, useEffect, useState } from 'react';

import {
  deleteSchedule,
  listSchedules,
  runScheduleNow,
  updateSchedule,
} from '../../core/api/schedules';
import type { Run, Schedule, SchedulePatch } from '../../core/api/types';
import { isActive } from '../runs/runStatus';
import { errorText, useSubmission, type Submission } from '../settings/useSubmission';

/** While a listed schedule's last run is active, the list is fetched again this often. */
export const ACTIVE_REFRESH_MS = 5000;
/** Otherwise, this often, so a schedule that fires while the page is open shows up. */
export const IDLE_REFRESH_MS = 30_000;

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
 * Keeps the list current: fetched again every `ACTIVE_REFRESH_MS` while a last run is queued
 * or running, else every `IDLE_REFRESH_MS`. Paused while a change is being saved, so a
 * refresh that began before it can never put the old state back; a failed refresh is
 * simply tried again.
 */
function useScheduleRefresh(
  schedules: Schedule[] | null,
  idle: boolean,
  setSchedules: (loaded: Schedule[]) => void,
) {
  const anyActive = (schedules ?? []).some(
    (schedule) => schedule.last_run !== null && isActive(schedule.last_run.status),
  );
  const loaded = schedules !== null;

  useEffect(() => {
    if (!loaded || !idle) return;
    const controller = new AbortController();
    const timer = setInterval(
      () => {
        listSchedules(undefined, controller.signal)
          .then((fresh) => {
            if (!controller.signal.aborted) setSchedules(fresh);
          })
          .catch(() => undefined);
      },
      anyActive ? ACTIVE_REFRESH_MS : IDLE_REFRESH_MS,
    );
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [loaded, idle, anyActive, setSchedules]);
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
  useScheduleRefresh(schedules, status === 'idle', setSchedules);

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
