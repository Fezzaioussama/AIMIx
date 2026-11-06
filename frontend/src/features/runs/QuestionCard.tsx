import { useState } from 'react';
import type { FormEvent } from 'react';

import type { RunApproval } from '../../core/api/types';
import { FOCUS_RING } from '../../core/ui/focus';
import { RUN_BUTTON } from './runButtons';
import { TimeLeft } from './TimeLeft';

const FIELD =
  'w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

interface QuestionCardProps {
  approval: RunApproval;
  /** Who asks: the step's name, and its agent's role when it has one. */
  askedBy: string;
  headingId: string;
  /** An answer is on its way. */
  busy?: boolean;
  /** Without both handlers the question is shown but cannot be answered here. */
  onAnswer?: (text: string) => void;
  onSkip?: () => void;
}

/** The question and its suggested answers, as the agent sent them (`ask_user`). */
export function questionOf(approval: RunApproval): { text: string; options: string[] } {
  const { question, options } = approval.arguments;
  return {
    text: typeof question === 'string' ? question : '',
    options: Array.isArray(options)
      ? options.filter((option): option is string => typeof option === 'string')
      : [],
  };
}

/**
 * One question an agent asked the person mid-run: the question as its heading, who
 * asks, the suggested answers as buttons, a box for an answer of their own, Skip, and
 * the time left. Doing nothing counts as skipping once the time is up.
 */
export function QuestionCard({
  approval,
  askedBy,
  headingId,
  busy,
  onAnswer,
  onSkip,
}: QuestionCardProps) {
  const { text, options } = questionOf(approval);
  const [typed, setTyped] = useState('');
  const answerable = onAnswer !== undefined && onSkip !== undefined;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (typed.trim() && onAnswer) onAnswer(typed.trim());
  }

  return (
    <section
      aria-labelledby={headingId}
      className="rounded-2xl border border-sky-400/40 bg-sky-400/[0.06] p-4"
    >
      <h3
        id={headingId}
        tabIndex={-1}
        className={`scroll-mt-[calc(var(--sticky-top,0px)+1rem)] rounded text-base font-semibold text-balance break-words text-slate-50 ${FOCUS_RING}`}
      >
        {text || 'Your team has a question for you'}
      </h3>
      <p className="mt-1 text-sm break-words text-slate-300">{askedBy} asks you.</p>
      {answerable ? (
        <form onSubmit={submit} className="mt-4 space-y-3">
          {options.length > 0 && (
            <div role="group" aria-label="Suggested answers" className="flex flex-wrap gap-2">
              {options.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={busy}
                  onClick={() => onAnswer(option)}
                  className={RUN_BUTTON.neutral}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          <label
            htmlFor={`${headingId}-answer`}
            className="block text-sm font-medium text-slate-300"
          >
            {options.length > 0 ? 'Or write your own answer' : 'Your answer'}
          </label>
          <textarea
            id={`${headingId}-answer`}
            value={typed}
            rows={2}
            disabled={busy}
            onChange={(event) => setTyped(event.target.value)}
            className={FIELD}
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={busy || typed.trim() === ''}
              className={RUN_BUTTON.resume}
            >
              Send answer
            </button>
            <button type="button" disabled={busy} onClick={onSkip} className={RUN_BUTTON.stop}>
              Skip
            </button>
          </div>
        </form>
      ) : (
        <p className="mt-3 text-xs text-slate-400">Answer it from the run in Runs.</p>
      )}
      <TimeLeft expiresAt={approval.expires_at} consequence="No answer counts as skipping it." />
    </section>
  );
}
