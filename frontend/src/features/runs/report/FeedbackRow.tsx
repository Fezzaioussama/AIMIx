import { ThumbsDown, ThumbsUp, type LucideIcon } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import type { Run, RunRating } from '../../../core/api/types';
import { Heading } from '../../../core/ui/Heading';
import { RUN_BUTTON } from '../runButtons';
import { isActive } from '../runStatus';
import type { RunControls } from '../useRun';
import { reportIds } from './reportModel';

const FIELD =
  'w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

/** A chosen thumb: the neutral button, lit. */
const CHOSEN = `${RUN_BUTTON.neutral} border-sky-400/50 bg-sky-500/10 text-sky-200`;

/** Each thumb's value, words and icon (Strategy + Registry, AGENTS §7). */
const THUMBS: { rating: Exclude<RunRating, null>; label: string; Icon: LucideIcon }[] = [
  { rating: 1, label: 'Useful', Icon: ThumbsUp },
  { rating: -1, label: 'Not useful', Icon: ThumbsDown },
];

interface FeedbackRowProps {
  run: Run;
  control: RunControls;
  level: 2 | 3;
}

/**
 * "Was this useful?" once the run has ended: two thumbs (press the chosen one again to
 * take it back) and a note for the next team, saved with the rating. The planner reads
 * the notes of your latest runs when it builds a new team. Nothing while the run works.
 */
export function FeedbackRow({ run, control, level }: FeedbackRowProps) {
  const [note, setNote] = useState(run.feedback);
  if (isActive(run.status)) return null;
  const headingId = `${reportIds(run.id).outcome}-feedback`;
  const fieldId = `${headingId}-note`;
  const dirty = note.trim() !== run.feedback;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void control.rate({ rating: run.rating, feedback: note.trim() });
  }

  return (
    <section aria-labelledby={headingId}>
      <Heading level={level} id={headingId} className="text-base font-semibold text-slate-100">
        Was this useful?
      </Heading>
      <div role="group" aria-label="Your rating" className="mt-3 flex flex-wrap gap-2">
        {THUMBS.map(({ rating, label, Icon }) => {
          const chosen = run.rating === rating;
          return (
            <button
              key={label}
              type="button"
              aria-pressed={chosen}
              disabled={control.busy}
              onClick={() =>
                void control.rate({ rating: chosen ? null : rating, feedback: run.feedback })
              }
              className={chosen ? CHOSEN : RUN_BUTTON.neutral}
            >
              <Icon aria-hidden="true" className="size-4" />
              {label}
            </button>
          );
        })}
      </div>
      <form onSubmit={submit} className="mt-3 space-y-2">
        <label htmlFor={fieldId} className="block text-sm text-slate-300">
          What should the next team do differently? The planner reads your notes.
        </label>
        <textarea
          id={fieldId}
          value={note}
          rows={2}
          maxLength={2000}
          disabled={control.busy}
          onChange={(event) => setNote(event.target.value)}
          className={FIELD}
        />
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={control.busy || !dirty} className={RUN_BUTTON.neutral}>
            Save note
          </button>
          {!dirty && run.feedback !== '' && (
            <p className="text-xs text-slate-400">Saved. The next team you plan will know.</p>
          )}
        </div>
      </form>
    </section>
  );
}
