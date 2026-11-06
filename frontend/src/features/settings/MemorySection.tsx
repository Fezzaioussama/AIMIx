import type { FormEvent } from 'react';

import { formatDateTime } from '../../core/time';
import { GlowButton } from '../../core/ui/GlowButton';
import { NoticeLine } from './NoticeLine';
import { useMemory } from './useMemory';

const FIELD =
  'w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-slate-100 outline-none transition-[border-color,box-shadow] focus:border-sky-400/60 focus:shadow-[0_0_0_3px_rgba(56,189,248,0.12)]';

const EXAMPLE =
  'For example: We are a bakery in Lyon. Our customers are busy parents. Write in French, warmly and briefly, and always end with a next step.';

/** Settings → Memory: what AIMIx keeps in mind in every chat, plan and run. */
export function MemorySection() {
  const { memory, draft, status, notice, dirty, edit, save } = useMemory();
  const busy = status !== 'idle';
  const max = memory?.max_chars ?? 0;
  const length = draft.trim().length;
  const over = max > 0 && length > max;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save();
  }

  return (
    <section aria-labelledby="memory-heading" className="mt-8">
      <h2 id="memory-heading" className="text-2xl font-bold tracking-tight">
        Memory
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        What AIMIx keeps in mind in every chat, plan and run: your business, who your work is for,
        the language and tone you want. Write it as you would brief a new colleague; the agents
        follow it unless a task says otherwise.
      </p>
      {status === 'loading' ? (
        <p className="text-sm text-slate-400">Loading your memory…</p>
      ) : (
        <form onSubmit={handleSubmit} noValidate className="space-y-3">
          <div>
            <label
              htmlFor="memory-instructions"
              className="mb-1 block text-sm font-medium text-slate-300"
            >
              Your instructions
            </label>
            <textarea
              id="memory-instructions"
              value={draft}
              rows={10}
              disabled={busy || memory === null}
              placeholder={EXAMPLE}
              aria-describedby="memory-count"
              onChange={(event) => edit(event.target.value)}
              className={FIELD}
            />
            <p
              id="memory-count"
              className={`mt-1 text-xs ${over ? 'text-red-400' : 'text-slate-400'}`}
            >
              {length.toLocaleString()} / {max.toLocaleString()} characters
              {memory?.updated_at && ` · saved ${formatDateTime(memory.updated_at)}`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <GlowButton
              type="submit"
              size="sm"
              busy={status === 'saving'}
              disabled={!dirty || busy || over}
            >
              Save memory
            </GlowButton>
            {notice && <NoticeLine notice={notice} />}
          </div>
        </form>
      )}
    </section>
  );
}
