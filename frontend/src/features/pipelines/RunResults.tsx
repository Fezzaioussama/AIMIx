import type { StepResult } from '../../core/api/types';
import { OutputCard } from './OutputCard';
import { StageArrow } from './StageArrow';
import { StageHeader } from './StageHeader';
import { modelLabel } from './modelLabel';
import { groupByStage } from './stages';

interface RunResultsProps {
  results: StepResult[];
  focusedStep: number | null;
}

/** Every step's output, grouped by stage; parallel outputs sit side by side. */
export function RunResults({ results, focusedStep }: RunResultsProps) {
  const stages = groupByStage(results, (result) => result.stage);

  return (
    <div>
      {stages.map((group, position) => (
        <div key={group.stage}>
          <StageHeader stage={group.stage} stepCount={group.items.length} />
          <div className={group.items.length > 1 ? 'grid gap-4 xl:grid-cols-2' : ''}>
            {group.items.map((result) => (
              <OutputCard
                key={result.step_order}
                heading={<StepHeading result={result} />}
                output={result.output}
                input={result.input_used}
                highlighted={focusedStep === result.step_order}
              />
            ))}
          </div>
          {position < stages.length - 1 && <StageArrow />}
        </div>
      ))}
    </div>
  );
}

function StepHeading({ result }: { result: StepResult }) {
  return (
    <>
      <span className="rounded-md bg-sky-400/15 px-2 py-1 text-xs font-semibold text-sky-400">
        Step {result.step_order}
      </span>
      <span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-400">
        {modelLabel(result.model)}
      </span>
    </>
  );
}
