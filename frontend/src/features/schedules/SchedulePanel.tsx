import { CalendarClock } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import type { Pipeline, Schedule } from '../../core/api/types';
import { Foldable, PanelToggle } from '../pipelines/FoldablePanel';
import { SCHEDULES_PATH } from './paths';
import { ScheduleForm } from './ScheduleForm';
import { describeTiming, emptyScheduleDraft, formatNextRun } from './scheduleDraft';
import { useCreateSchedule } from './useCreateSchedule';

export interface SchedulePanelProps {
  /** The pipeline on screen; only a saved one can be scheduled. */
  pipeline: Pipeline;
  /** It has edits that are not saved: a schedule runs the saved version. */
  dirty: boolean;
  /** The panel title's heading level. */
  headingLevel?: 2 | 3;
  className?: string;
}

const LINK =
  'rounded-sm text-sky-300 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400';

/**
 * "Schedule this pipeline": a foldable panel under the builder's title that makes the
 * pipeline run by itself — every hour, day, weekday, week or month — with the run inputs
 * filled in once. A schedule always runs the pipeline as last saved. Opening another
 * pipeline starts the panel afresh.
 */
export function SchedulePanel(props: SchedulePanelProps) {
  return <PipelineSchedulePanel key={props.pipeline.id ?? 'unsaved'} {...props} />;
}

function PipelineSchedulePanel({
  pipeline,
  dirty,
  headingLevel = 2,
  className = '',
}: SchedulePanelProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  // The body is built the first time the panel opens and kept after, so a page that never
  // opens it asks the server nothing (the form previews the next run as it is filled in).
  const [built, setBuilt] = useState(false);

  return (
    <section
      aria-labelledby={`${id}-title`}
      className={`rounded-2xl border border-sky-400/20 bg-[linear-gradient(135deg,rgba(56,189,248,0.08),rgba(99,102,241,0.05))] ${className}`}
    >
      <PanelToggle
        id={id}
        level={headingLevel}
        icon={<CalendarClock aria-hidden="true" className="size-4 shrink-0 text-sky-300" />}
        title="Schedule this pipeline"
        open={open}
        onToggle={() => {
          setOpen(!open);
          setBuilt(true);
        }}
      />
      <Foldable id={`${id}-body`} open={open}>
        {built && <PanelBody id={id} pipeline={pipeline} dirty={dirty} />}
      </Foldable>
    </section>
  );
}

function PanelBody({
  id,
  pipeline,
  dirty,
}: { id: string } & Pick<SchedulePanelProps, 'pipeline' | 'dirty'>) {
  const { busy, error, created, create } = useCreateSchedule(pipeline.id, pipeline.inputs);
  const initial = useMemo(() => emptyScheduleDraft(), []);

  if (pipeline.id === undefined) {
    return (
      <p className="text-sm text-slate-300">Save this pipeline first, then you can schedule it.</p>
    );
  }
  return (
    <>
      <p className="mb-4 text-sm text-slate-300">
        Run this pipeline on its own, as often as you like. Each run uses the pipeline as last
        saved, and shows up in{' '}
        <Link to="/runs" className={LINK}>
          Runs
        </Link>{' '}
        marked as scheduled.
      </p>
      {/* A new form after each schedule, so pressing the button twice never saves it twice. */}
      <ScheduleForm
        key={created?.id ?? 'new'}
        idBase={`${id}-form`}
        label="New schedule"
        inputs={pipeline.inputs}
        initial={initial}
        submitLabel="Schedule it"
        busy={busy}
        blocked={dirty ? 'Save your changes first: a schedule runs the saved version.' : ''}
        onSubmit={(draft) => void create(draft)}
      />
      <Outcome created={created} error={error} />
      <p className="mt-4 text-sm">
        <Link to={SCHEDULES_PATH} className={LINK}>
          See all your schedules
        </Link>
      </p>
    </>
  );
}

/** What saving did: a polite line that is always in the page, and an alert for a refusal. */
function Outcome({ created, error }: { created: Schedule | null; error: string }) {
  const next = created?.next_run_at
    ? ` Next run: ${formatNextRun(created.next_run_at, created.timezone)}.`
    : '';
  return (
    <>
      <p role="status" className={created ? 'mt-4 text-sm text-emerald-300' : 'sr-only'}>
        {created && `Scheduled: ${describeTiming(created)}.${next}`}
      </p>
      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}
    </>
  );
}
