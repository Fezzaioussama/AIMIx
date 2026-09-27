import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import type { StepResult } from '../../core/api/types';
import { StageArrow } from './StageArrow';
import { StageHeader } from './StageHeader';
import { modelLabel } from './modelLabel';
import { groupByStage } from './stages';

const cardClass = 'rounded-2xl border border-white/10 bg-slate-800/50 p-8';

interface RunResultsProps {
  results: StepResult[];
  finalOutput: string;
}

/** Every step's output, grouped by stage; parallel outputs sit side by side. */
export function RunResults({ results, finalOutput }: RunResultsProps) {
  if (results.length === 0) return null;
  const stages = groupByStage(results, (result) => result.stage);

  return (
    <div>
      {stages.map((group, position) => (
        <div key={group.stage}>
          <StageHeader stage={group.stage} stepCount={group.items.length} />
          <div className={group.items.length > 1 ? 'grid gap-4 lg:grid-cols-2' : ''}>
            {group.items.map((result) => (
              <StepOutput key={result.step_order} result={result} />
            ))}
          </div>
          {position < stages.length - 1 && <StageArrow />}
        </div>
      ))}

      {finalOutput && (
        <div className={`${cardClass} mt-8`}>
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

function StepOutput({ result }: { result: StepResult }) {
  return (
    <div className={`${cardClass} min-w-0`}>
      <div className="mb-4 flex items-center gap-3">
        <span className="rounded-md bg-sky-400/15 px-2 py-1 text-xs font-semibold text-sky-400">
          Step {result.step_order}
        </span>
        <span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-400">
          {modelLabel(result.model)}
        </span>
      </div>
      <p className="mb-3 text-sm text-slate-400">
        <strong className="text-slate-300">Input:</strong> {result.input_used.slice(0, 100)}
        {result.input_used.length > 100 ? '…' : ''}
      </p>
      <div
        className="prose-output text-slate-100"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(result.output) }}
      />
    </div>
  );
}
