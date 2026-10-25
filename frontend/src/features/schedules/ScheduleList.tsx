import { useEffect, useRef, useState } from 'react';

import type { Run, Schedule } from '../../core/api/types';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { ScheduleCard, editButtonId } from './ScheduleCard';
import { ScheduleForm } from './ScheduleForm';
import { draftFromSchedule, toPatch, type ScheduleDraft } from './scheduleDraft';
import type { SchedulesState } from './useSchedules';

interface ScheduleListProps {
  schedules: Schedule[];
  busy: boolean;
  actions: SchedulesState['actions'];
  /** Open the run "Run now" started. */
  onStarted: (run: Run) => void;
}

/** Puts focus back on a schedule's Edit button once its form closes. */
function useRestoreFocus(editing: number | null) {
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (editing !== null) last.current = editing;
    else if (last.current !== null) {
      document.getElementById(editButtonId(last.current))?.focus();
      last.current = null;
    }
  }, [editing]);
}

/** Each schedule as a card, or as its form while it is being edited. */
export function ScheduleList({ schedules, busy, actions, onStarted }: ScheduleListProps) {
  const [editing, setEditing] = useState<number | null>(null);
  useRestoreFocus(editing);

  async function save(schedule: Schedule, draft: ScheduleDraft) {
    const saved = await actions.update(schedule, toPatch(schedule.pipeline_inputs, draft));
    if (saved) setEditing(null);
  }

  async function runNow(schedule: Schedule) {
    const run = await actions.runNow(schedule);
    if (run) onStarted(run);
  }

  return (
    <ul className="grid gap-4 lg:grid-cols-2">
      {schedules.map((schedule, index) => (
        // The form takes the whole row, as wide as the builder's, instead of half of it.
        <li
          key={schedule.id}
          className={`min-w-0 ${editing === schedule.id ? 'lg:col-span-2' : ''}`}
        >
          {editing === schedule.id ? (
            <SpotlightCard variant="highlighted" className="p-5">
              <h3 className="mb-4 text-lg font-semibold break-words">
                Edit the schedule of {schedule.pipeline_name}
              </h3>
              <ScheduleForm
                idBase={`schedule-form-${schedule.id}`}
                label={`Edit the schedule of ${schedule.pipeline_name}`}
                inputs={schedule.pipeline_inputs}
                initial={draftFromSchedule(schedule)}
                submitLabel="Save changes"
                busy={busy}
                onSubmit={(draft) => void save(schedule, draft)}
                onCancel={() => setEditing(null)}
              />
            </SpotlightCard>
          ) : (
            <AnimatedContent distance={18} delay={Math.min(index, 6) * 0.05}>
              <ScheduleCard
                schedule={schedule}
                busy={busy}
                onToggle={(enabled) => void actions.setEnabled(schedule, enabled)}
                onRunNow={() => void runNow(schedule)}
                onEdit={() => setEditing(schedule.id)}
                onDelete={() => void actions.remove(schedule)}
              />
            </AnimatedContent>
          )}
        </li>
      ))}
    </ul>
  );
}
