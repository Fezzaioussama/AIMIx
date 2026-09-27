import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import type { StepResult } from '../../core/api/types';
import { modelLabel } from './modelLabel';

const cardClass = 'mb-8 rounded-2xl border border-white/10 bg-slate-800/50 p-8';

interface RunResultsProps {
  results: StepResult[];
  finalOutput: string;
}

export function RunResults({ results, finalOutput }: RunResultsProps) {
  if (results.length === 0) return null;

  return (
    <div>
      {results.map((result) => (
        <div key={result.step_order} className={cardClass}>
          <div className="mb-4 flex items-center gap-3">
            <span className="rounded-md bg-sky-400/15 px-2 py-1 text-xs font-semibold text-sky-400">
              Step {result.step_order}
            </span>
            <span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-400">
              {modelLabel(result.model)}
            </span>
          </div>
          <p className="mb-3 text-sm text-slate-400">
            <strong className="text-slate-300">Input:</strong>{' '}
            {result.input_used.slice(0, 100)}
            {result.input_used.length > 100 ? '…' : ''}
          </p>
          <div
            className="prose-output text-slate-100"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(result.output) }}
          />
        </div>
      ))}

      {finalOutput && (
        <div className={cardClass}>
          <h2 className="mb-4 text-xl font-semibold text-slate-50">Final Output</h2>
          <div
            className="prose-output text-slate-100"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(finalOutput) }}
          />
        </div>
      )}
    </div>
  );
}
