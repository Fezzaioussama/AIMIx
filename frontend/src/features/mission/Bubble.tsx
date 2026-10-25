import type { ReactNode } from 'react';

import { Spinner } from '../../core/ui/Spinner';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { SECONDARY_BUTTON } from '../pipelines/buttonStyles';

const TONES = {
  info: 'border-white/10 bg-slate-900/70 text-slate-100',
  error: 'border-red-400/30 bg-red-500/10 text-red-200',
} as const;

interface BubbleProps {
  tone?: keyof typeof TONES;
  className?: string;
  children: ReactNode;
}

/** One answer from AIMIx, as a speech bubble. */
export function Bubble({ tone = 'info', className = '', children }: BubbleProps) {
  return (
    <div
      className={`min-w-0 rounded-2xl rounded-tl-md border px-4 py-3 text-sm leading-relaxed break-words ${TONES[tone]} ${className}`}
    >
      {children}
    </div>
  );
}

/** "Working on it…" with a way to stop. */
export function Working({ children, onStop }: { children: ReactNode; onStop: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Spinner decorative className="size-4" />
      <ShinyText className="text-slate-300/90">{children}</ShinyText>
      <button type="button" onClick={onStop} className={SECONDARY_BUTTON}>
        Stop
      </button>
    </div>
  );
}

/** A quiet link-like button inside an answer, e.g. "See the team". */
export const ANSWER_ACTION =
  'inline-flex items-center gap-1.5 rounded-lg text-sm font-medium text-sky-300 underline-offset-4 transition-colors hover:text-sky-200 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400';
