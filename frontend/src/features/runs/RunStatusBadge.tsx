import type { RunStatus } from '../../core/api/types';

/** Each run status's words and colours (sky for work in progress, as on the diagram). */
export const RUN_STATUS_STYLES: Record<RunStatus, { label: string; badge: string; dot: string }> = {
  queued: {
    label: 'Queued',
    badge: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
    dot: 'bg-indigo-300',
  },
  running: {
    label: 'Running',
    badge: 'border-sky-400/40 bg-sky-400/10 text-sky-200',
    dot: 'bg-sky-400 motion-safe:animate-pulse',
  },
  // Amber and pulsing: the one active status that needs the person, not the server.
  waiting: {
    label: 'Waiting for you',
    badge: 'border-amber-400/50 bg-amber-400/15 text-amber-200',
    dot: 'bg-amber-400 motion-safe:animate-pulse',
  },
  succeeded: {
    label: 'Done',
    badge: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200',
    dot: 'bg-emerald-400',
  },
  failed: {
    label: 'Failed',
    badge: 'border-red-400/40 bg-red-400/10 text-red-200',
    dot: 'bg-red-400',
  },
  cancelled: {
    label: 'Stopped',
    badge: 'border-amber-400/40 bg-amber-400/10 text-amber-200',
    dot: 'bg-amber-400',
  },
  interrupted: {
    label: 'Interrupted',
    badge: 'border-purple-400/40 bg-purple-400/10 text-purple-200',
    dot: 'bg-purple-400',
  },
};

/** A run's status as a small pill: a dot and a word. */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  const style = RUN_STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.badge}`}
    >
      <span className={`size-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {style.label}
    </span>
  );
}
