import { useEffect, useRef, useState, type ReactNode } from 'react';

import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import { useCopyToClipboard } from './useCopyToClipboard';

/** Outputs longer than this start folded so a page of results stays scannable. */
const FOLD_THRESHOLD_CHARS = 1500;

const toolButton =
  'rounded-md border border-white/10 px-2.5 py-1 text-xs text-slate-300 transition-colors hover:bg-white/10';

interface OutputCardProps {
  heading: ReactNode;
  output: string;
  input?: string;
  highlighted?: boolean;
  foldable?: boolean;
}

/** One model output with rendered/raw views, copy, the input it saw, and folding. */
export function OutputCard({
  heading,
  output,
  input,
  highlighted = false,
  foldable = true,
}: OutputCardProps) {
  const [raw, setRaw] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const { copied, copy } = useCopyToClipboard();
  const card = useRef<HTMLDivElement>(null);
  const folded = foldable && !expanded && output.length > FOLD_THRESHOLD_CHARS;

  // Bring the card into view when the diagram points at it.
  useEffect(() => {
    if (highlighted) card.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [highlighted]);

  return (
    <div
      ref={card}
      className={`min-w-0 scroll-mt-6 rounded-2xl border bg-slate-800/50 p-6 transition-shadow ${
        highlighted ? 'border-sky-400/60 ring-2 ring-sky-400/40' : 'border-white/10'
      }`}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">{heading}</div>
        <div className="flex gap-2">
          <button type="button" className={toolButton} onClick={() => setRaw((value) => !value)}>
            {raw ? 'Rendered' : 'Raw'}
          </button>
          <button type="button" className={toolButton} onClick={() => void copy(output)}>
            {copied ? 'Copied ✓' : 'Copy'}
          </button>
        </div>
      </div>

      {input !== undefined && (
        <details className="mb-4 rounded-lg bg-slate-900/60 px-4 py-2 text-sm text-slate-400">
          <summary className="cursor-pointer select-none text-slate-300">Input</summary>
          <pre className="mt-2 max-h-60 overflow-auto font-sans whitespace-pre-wrap">{input}</pre>
        </details>
      )}

      <div className={`relative ${folded ? 'max-h-96 overflow-hidden' : ''}`}>
        {raw ? (
          <pre className="overflow-x-auto rounded-lg bg-slate-950/60 p-4 text-sm whitespace-pre-wrap text-slate-200">
            {output}
          </pre>
        ) : (
          <div
            className="prose-output text-slate-100"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(output) }}
          />
        )}
        {folded && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-slate-800 to-transparent" />
        )}
      </div>

      {foldable && output.length > FOLD_THRESHOLD_CHARS && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 text-sm font-medium text-sky-400 hover:text-sky-300"
        >
          {expanded ? 'Show less' : 'Show full output'}
        </button>
      )}
    </div>
  );
}
