import type { ReactNode } from 'react';

import type { Run, RunStatus } from '../../core/api/types';
import { useNow } from '../../core/hooks/useNow';
import { elapsedMs, formatDuration } from '../../core/time';
import { stepLabel } from '../pipelines/stages';
import { RUN_STATUS_STYLES, RunStatusBadge } from './RunStatusBadge';
import { RUN_BUTTON } from './runButtons';
import { finishedStepCount, isActive, isResumable } from './runStatus';

/** One plain line on where the run is, when there is something to say. */
const STATUS_NOTES: Partial<Record<RunStatus, string>> = {
  queued: 'It starts as soon as a slot is free.',
  running: 'It keeps running if you leave this page.',
  waiting: 'This run is waiting for you. Approve or decline the action below to let it go on.',
  cancelled: 'You stopped this run.',
  interrupted: 'The server restarted while this run was in progress.',
};

interface LiveRunHeaderProps {
  run: Run;
  onStop?: () => void;
  onResume?: () => void;
  /** A stop or resume is in flight. */
  busy?: boolean;
  /** Why the last fetch, stop or resume failed. */
  error?: string;
  /** More controls next to Stop and Resume. */
  actions?: ReactNode;
  /** A line under the status, e.g. that the run used an earlier version. */
  note?: ReactNode;
}

/** A run's status bar: status, progress and time, Stop and Resume, and why it stopped. */
export function LiveRunHeader({
  run,
  onStop,
  onResume,
  busy = false,
  error = '',
  actions,
  note,
}: LiveRunHeaderProps) {
  const active = isActive(run.status);
  const now = useNow(active);
  const elapsed = elapsedMs(run.started_at, run.finished_at, now);
  const progress = `${finishedStepCount(run)} of ${run.steps.length} steps done`;

  return (
    <div className="mt-6 rounded-2xl border border-white/10 bg-slate-900/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <RunStatusBadge status={run.status} />
          <span className="text-slate-200">{progress}</span>
          {elapsed !== null && (
            <span className="text-slate-400 tabular-nums">{formatDuration(elapsed)}</span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {active && onStop && (
            <button type="button" onClick={onStop} disabled={busy} className={RUN_BUTTON.stop}>
              Stop
            </button>
          )}
          {isResumable(run.status) && onResume && (
            <button type="button" onClick={onResume} disabled={busy} className={RUN_BUTTON.resume}>
              Resume
            </button>
          )}
          {actions}
        </div>
      </div>
      <p className="sr-only" aria-live="polite">
        {`Run ${RUN_STATUS_STYLES[run.status].label.toLowerCase()}. ${progress}.`}
      </p>
      <RunNotes run={run} />
      {note}
      {error && (
        <p role="alert" className="mt-3 text-sm text-amber-300">
          {error}
        </p>
      )}
    </div>
  );
}

function RunNotes({ run }: { run: Run }) {
  const failedStep = run.steps.find((step) => step.status === 'failed');
  const statusNote = STATUS_NOTES[run.status];
  return (
    <>
      {statusNote && <p className="mt-3 text-sm text-slate-300">{statusNote}</p>}
      {run.error && (
        <p role="alert" className="mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300">
          <span className="font-semibold">
            {failedStep
              ? `${stepLabel({ order: failedStep.step_order, title: failedStep.title })} failed.`
              : 'The run failed.'}
          </span>{' '}
          <span className="break-words">{run.error.detail}</span>
        </p>
      )}
      {isResumable(run.status) && (
        <p className="mt-2 text-xs text-slate-400">
          Resume continues where it stopped and keeps the steps already done.
        </p>
      )}
    </>
  );
}
