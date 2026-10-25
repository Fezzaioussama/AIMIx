import type { ArgumentRow } from './approvalFormat';

/** What a tool call will use, one labelled value per argument; a long value folds. */
export function ArgumentList({ rows }: { rows: ArgumentRow[] }) {
  if (rows.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">It uses nothing else.</p>;
  }
  return (
    <div
      role="group"
      aria-label="What the action will use"
      className="mt-3 rounded-xl border border-white/10 bg-slate-950/50 px-3 py-2.5"
    >
      <dl className="space-y-2">
        {rows.map((row) => (
          <div key={row.key}>
            <dt className="text-xs font-semibold tracking-wide break-all text-slate-400 uppercase">
              {row.key}
            </dt>
            <dd className="mt-0.5 text-sm text-slate-100">
              {row.folded ? <FoldedValue row={row} /> : <Value text={row.text} />}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Value({ text }: { text: string }) {
  return <span className="break-words whitespace-pre-wrap">{text}</span>;
}

/** A long value: its start, and the whole of it one click away (native, so keyboard-friendly). */
function FoldedValue({ row }: { row: ArgumentRow }) {
  return (
    <details className="group">
      <summary className="cursor-pointer list-none rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
        <span className="break-words group-open:hidden">{row.preview} </span>
        <span className="text-sky-300 underline-offset-2 group-open:hidden hover:underline">
          Show all
        </span>
        <span className="hidden text-sky-300 underline-offset-2 group-open:inline hover:underline">
          Show less
        </span>
      </summary>
      <pre className="mt-1.5 max-h-72 overflow-auto font-sans text-sm break-words whitespace-pre-wrap">
        {row.text}
      </pre>
    </details>
  );
}
