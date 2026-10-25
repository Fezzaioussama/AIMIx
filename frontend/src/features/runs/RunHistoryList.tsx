import { Link } from 'react-router-dom';

import type { RunSummary } from '../../core/api/types';
import { elapsedMs, formatDateTime, formatDuration } from '../../core/time';
import { CostText } from '../../core/ui/CostText';
import { describeCost } from '../../core/usageFormat';
import { RunStatusBadge } from './RunStatusBadge';
import { isActive } from './runStatus';

interface RunHistoryListProps {
  items: RunSummary[];
  total: number;
  selectedId: number | null;
  loading: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

/** How long a listed run took, or that it is still going. */
function durationText(run: RunSummary): string {
  if (run.status === 'queued') return 'Waiting to start';
  if (run.status === 'waiting') return 'Needs your OK';
  if (isActive(run.status)) return 'In progress';
  const elapsed = elapsedMs(run.started_at, run.finished_at, Date.now());
  return elapsed === null ? 'Did not start' : formatDuration(elapsed);
}

/** The run history: each run's pipeline, status, start and duration; opens it. */
export function RunHistoryList({
  items,
  total,
  selectedId,
  loading,
  loadingMore,
  onLoadMore,
}: RunHistoryListProps) {
  if (loading) return <p className="text-sm text-slate-400">Loading your runs…</p>;
  if (items.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-white/10 p-6 text-sm text-slate-300">
        No runs yet. Open a pipeline and choose{' '}
        <Link to="/pipeline" className="text-sky-300 underline-offset-2 hover:underline">
          Run Pipeline
        </Link>
        ; every run shows up here.
      </p>
    );
  }
  return (
    <nav aria-label="Run history">
      <ul className="space-y-2">
        {items.map((run) => (
          <li key={run.id}>
            <RunLink run={run} selected={run.id === selectedId} />
          </li>
        ))}
      </ul>
      {items.length < total && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingMore}
          className="mt-3 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-sky-400 disabled:opacity-60"
        >
          {loadingMore ? 'Loading…' : `Show more (${total - items.length} left)`}
        </button>
      )}
    </nav>
  );
}

function RunLink({ run, selected }: { run: RunSummary; selected: boolean }) {
  const cost = describeCost(run.usage);
  return (
    <Link
      to={`/runs/${run.id}`}
      aria-current={selected ? 'page' : undefined}
      className={`block rounded-xl border px-3 py-2.5 transition-colors focus-visible:outline-2 focus-visible:outline-sky-400 ${
        selected
          ? 'border-sky-400/40 bg-sky-400/10'
          : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.07]'
      }`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium text-slate-100">{run.pipeline_name}</span>
        <RunStatusBadge status={run.status} />
      </span>
      <span className="mt-1 flex flex-wrap items-center justify-between gap-x-2 text-xs text-slate-400">
        <span>{formatDateTime(run.started_at ?? run.created_at)}</span>
        <span className="tabular-nums">
          {durationText(run)}
          {cost && (
            <>
              {' · '}
              <CostText view={cost} compact />
            </>
          )}
        </span>
      </span>
    </Link>
  );
}
