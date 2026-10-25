import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import type { Schedule } from '../../core/api/types';
import { formatDateTime } from '../../core/time';
import { ToggleSwitch } from '../../core/ui/ToggleSwitch';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { RunStatusBadge } from '../runs/RunStatusBadge';
import { actionButtonClass } from '../settings/actionButton';
import { describeTiming, formatNextRun } from './scheduleDraft';

interface ScheduleCardProps {
  schedule: Schedule;
  /** Something is being saved: no second change at the same time. */
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onRunNow: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

/** The id of a schedule's Edit button, so focus can return to it when the form closes. */
export const editButtonId = (scheduleId: number) => `schedule-edit-${scheduleId}`;

function DeleteConfirm({
  busy,
  onConfirm,
  onCancel,
}: {
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      role="group"
      aria-label="Delete this schedule?"
      className="mt-4 rounded-lg border border-red-400/30 bg-red-500/5 p-3 text-sm"
    >
      <p className="text-slate-200">
        Delete this schedule? It stops running. The runs it already started stay in your history.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Delete schedule
        </button>
        <button type="button" onClick={onCancel} autoFocus className={actionButtonClass()}>
          Keep it
        </button>
      </div>
    </div>
  );
}

/** When it runs next, or why it will not. */
function nextRunText(schedule: Schedule): string {
  if (!schedule.enabled || schedule.next_run_at === null) {
    return 'Off. It will not run until you turn it on.';
  }
  return formatNextRun(schedule.next_run_at, schedule.timezone);
}

function LastRun({ schedule }: { schedule: Schedule }) {
  const { last_run: last } = schedule;
  if (last === null) return <>No runs yet</>;
  return (
    <Link
      to={`/runs/${last.id}`}
      className="inline-flex flex-wrap items-center gap-2 text-slate-100 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
    >
      <span className="sr-only">Open the run from </span>
      <span>{formatDateTime(last.created_at)}</span>
      <RunStatusBadge status={last.status} />
    </Link>
  );
}

/** One schedule: what it runs and how often, when it runs next, how the last run went. */
export function ScheduleCard({
  schedule,
  busy,
  onToggle,
  onRunNow,
  onEdit,
  onDelete,
}: ScheduleCardProps) {
  const [confirming, setConfirming] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const headingId = `schedule-${schedule.id}`;

  return (
    <SpotlightCard as="section" aria-labelledby={headingId} className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={headingId} className="text-lg font-semibold break-words">
            <Link
              to="/pipeline"
              state={{ pipelineId: schedule.pipeline_id }}
              className="underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
            >
              {schedule.pipeline_name}
            </Link>
          </h3>
          <p className="mt-0.5 text-sm text-slate-200">{describeTiming(schedule)}</p>
        </div>
        <ToggleSwitch
          checked={schedule.enabled}
          label={`Run ${schedule.pipeline_name} on this schedule`}
          disabled={busy}
          onChange={onToggle}
        />
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-slate-400">Next run</dt>
        <dd className="text-slate-100">{nextRunText(schedule)}</dd>
        <dt className="text-slate-400">Last run</dt>
        <dd className="text-slate-300">
          <LastRun schedule={schedule} />
        </dd>
      </dl>
      {schedule.last_error && (
        <p className="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          The last time, it could not start: {schedule.last_error}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onRunNow}
          disabled={busy}
          className={actionButtonClass('accent')}
        >
          Run now
        </button>
        <button
          id={editButtonId(schedule.id)}
          type="button"
          onClick={onEdit}
          disabled={busy}
          className={actionButtonClass()}
        >
          Edit
        </button>
        <button
          ref={deleteButton}
          type="button"
          onClick={() => setConfirming(true)}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Delete
        </button>
      </div>
      {confirming && (
        <DeleteConfirm
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => {
            setConfirming(false);
            deleteButton.current?.focus();
          }}
        />
      )}
    </SpotlightCard>
  );
}
