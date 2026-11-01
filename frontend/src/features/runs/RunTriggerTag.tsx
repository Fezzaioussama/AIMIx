import { CalendarClock, Webhook, type LucideIcon } from 'lucide-react';

import type { RunTrigger } from '../../core/api/types';

/** The runs worth marking: those nobody started from a screen. */
const TRIGGER_TAGS: Partial<Record<RunTrigger, { icon: LucideIcon; label: string }>> = {
  schedule: { icon: CalendarClock, label: 'Scheduled' },
  webhook: { icon: Webhook, label: 'From a webhook' },
};

export function hasTriggerTag(trigger: RunTrigger): boolean {
  return trigger in TRIGGER_TAGS;
}

/** Marks a run a schedule or a webhook started, with a small icon; any other run shows nothing. */
export function RunTriggerTag({ trigger }: { trigger: RunTrigger }) {
  const tag = TRIGGER_TAGS[trigger];
  if (!tag) return null;
  const Icon = tag.icon;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-sky-300">
      <Icon aria-hidden="true" className="size-3.5" />
      {tag.label}
    </span>
  );
}
