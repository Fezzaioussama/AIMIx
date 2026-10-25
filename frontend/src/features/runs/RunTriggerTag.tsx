import { CalendarClock } from 'lucide-react';

import type { RunTrigger } from '../../core/api/types';

/** Marks a run that a schedule started, with a small clock; any other run shows nothing. */
export function RunTriggerTag({ trigger }: { trigger: RunTrigger }) {
  if (trigger !== 'schedule') return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-sky-300">
      <CalendarClock aria-hidden="true" className="size-3.5" />
      Scheduled
    </span>
  );
}
