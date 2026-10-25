import { useState, type FormEvent } from 'react';

import type { PipelineInput } from '../../core/api/types';
import { Spinner } from '../../core/ui/Spinner';
import { PRIMARY_BUTTON, SECONDARY_BUTTON } from '../pipelines/buttonStyles';
import { RunInputFields } from '../pipelines/RunInputCard';
import { ScheduleFields } from './ScheduleFields';
import {
  describeTiming,
  formatNextRun,
  isTimeValid,
  scheduleProblem,
  timingOf,
  type ScheduleDraft,
} from './scheduleDraft';
import { useSchedulePreview } from './useSchedulePreview';

/**
 * The free-text field's name. The builder page also holds the run card's "Run input", so
 * the two must not read alike to assistive technology.
 */
export const INPUT_LABEL = 'Input for each scheduled run';

interface ScheduleFormProps {
  /** Makes each field's id unique on the page. */
  idBase: string;
  /** What names the form for assistive technology. */
  label: string;
  /** The pipeline's named inputs; none means one free-text input. */
  inputs: PipelineInput[];
  /** The values it starts with; a form does not follow later changes (key it to reset). */
  initial: ScheduleDraft;
  submitLabel: string;
  /** Saving is in flight. */
  busy: boolean;
  /** Why saving is not possible right now; the button waits and the reason shows. */
  blocked?: string;
  onSubmit: (draft: ScheduleDraft) => void;
  onCancel?: () => void;
}

/**
 * The schedule form shared by the builder's panel (a new schedule) and the Schedules list
 * (an edit): when it runs, said in words with the next run the server works out, and what
 * each run is given — asked the same way a manual run asks.
 */
export function ScheduleForm({
  idBase,
  label,
  inputs,
  initial,
  submitLabel,
  busy,
  blocked = '',
  onSubmit,
  onCancel,
}: ScheduleFormProps) {
  const [draft, setDraft] = useState(initial);
  const [tried, setTried] = useState(false);
  const problem = scheduleProblem(inputs, draft);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (!problem && !blocked) onSubmit(draft);
  }

  return (
    <form onSubmit={handleSubmit} noValidate aria-label={label}>
      <ScheduleFields idBase={idBase} draft={draft} disabled={busy} onChange={setDraft} />
      <WhenSummary draft={draft} />
      <fieldset className="mt-5 min-w-0">
        <legend className="mb-2 text-sm font-medium text-slate-200">What each run is given</legend>
        <RunInputFields
          inputs={inputs}
          draft={draft.run}
          disabled={busy}
          onDraftChange={(run) => setDraft({ ...draft, run })}
          label={INPUT_LABEL}
        />
      </fieldset>
      {tried && problem && (
        <p role="alert" className="mb-3 text-sm text-amber-300">
          {problem}
        </p>
      )}
      {blocked && <p className="mb-3 text-sm text-sky-300">{blocked}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={busy || Boolean(blocked)} className={PRIMARY_BUTTON}>
          {busy && <Spinner decorative className="size-4" />}
          {busy ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} disabled={busy} className={SECONDARY_BUTTON}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

/** One polite live region: the timing in words, and the next run the server works out. */
function WhenSummary({ draft }: { draft: ScheduleDraft }) {
  const complete = isTimeValid(draft.time);
  const preview = useSchedulePreview(complete ? timingOf(draft) : null);

  let next = 'Working out the next run…';
  if (preview.error) next = preview.error;
  else if (preview.nextRunAt)
    next = `Next run: ${formatNextRun(preview.nextRunAt, draft.timezone)}`;

  return (
    <div
      role="status"
      className="mt-4 rounded-xl border border-sky-400/25 bg-sky-400/5 px-4 py-3 text-sm"
    >
      {complete ? (
        <>
          <p className="font-medium text-slate-100">{describeTiming(timingOf(draft))}</p>
          <p className={`mt-0.5 ${preview.error ? 'text-amber-300' : 'text-slate-300'}`}>{next}</p>
        </>
      ) : (
        <p className="text-slate-300">Choose a time to see when it runs.</p>
      )}
    </div>
  );
}
