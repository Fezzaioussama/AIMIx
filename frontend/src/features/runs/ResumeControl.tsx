import { useId, useState, type FormEvent } from 'react';

import type { Run, RunBudget } from '../../core/api/types';
import { RUN_BUTTON } from './runButtons';
import {
  limitBudget,
  limitProblem,
  limitReached,
  suggestedLimit,
  usedText,
  type LimitKind,
} from './runBudget';

interface ResumeControlProps {
  run: Run;
  /** Continue the run, under new limits when given. */
  onResume: (budget?: RunBudget) => void;
  busy: boolean;
}

const FIELD =
  'w-24 rounded-lg border border-white/15 bg-slate-950/60 px-2 py-1.5 text-sm tabular-nums outline-none focus:border-sky-400/60 focus-visible:outline-2 focus-visible:outline-sky-400';

/**
 * Resume a stopped run. One that stopped at its spending limit cannot continue
 * under the same limit, so it asks for a higher one first.
 */
export function ResumeControl({ run, onResume, busy }: ResumeControlProps) {
  const kind = limitReached(run);
  if (kind === null) {
    return (
      <button
        type="button"
        onClick={() => onResume()}
        disabled={busy}
        className={RUN_BUTTON.resume}
      >
        Resume
      </button>
    );
  }
  return <RaiseLimit run={run} kind={kind} onResume={onResume} busy={busy} />;
}

interface RaiseLimitProps extends ResumeControlProps {
  kind: LimitKind;
}

/** "Raise the limit to [ ] Resume": the new limit is the only thing asked. */
function RaiseLimit({ run, kind, onResume, busy }: RaiseLimitProps) {
  const id = useId();
  const [text, setText] = useState(() => suggestedLimit(run, kind));
  const problem = limitProblem(run, kind, text);
  const label = kind === 'cost' ? 'Raise the limit to' : 'Raise the token limit to';

  function submit(event: FormEvent) {
    event.preventDefault();
    const budget = limitBudget(kind, text);
    if (problem === null && budget !== null) onResume(budget);
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <label htmlFor={id} className="text-sm text-slate-200">
        {label}
      </label>
      <span className="flex items-center gap-1">
        {kind === 'cost' && (
          <span aria-hidden="true" className="text-slate-300">
            $
          </span>
        )}
        <input
          id={id}
          type="text"
          inputMode={kind === 'cost' ? 'decimal' : 'numeric'}
          value={text}
          disabled={busy}
          aria-invalid={problem !== null}
          aria-describedby={`${id}-note`}
          onChange={(event) => setText(event.target.value)}
          className={FIELD}
        />
      </span>
      <button type="submit" disabled={busy || problem !== null} className={RUN_BUTTON.resume}>
        Resume
      </button>
      <p
        id={`${id}-note`}
        aria-live="polite"
        className={`basis-full text-xs ${problem ? 'text-amber-300' : 'text-slate-400'}`}
      >
        {problem ?? `It has used ${usedText(run, kind)} so far.`}
      </p>
    </form>
  );
}
