import type { StepResult } from '../../core/api/types';
import { OutputCard } from './OutputCard';
import { StageArrow } from './StageArrow';
import { StageHeader } from './StageHeader';
import { StepHeading } from './StepHeading';
import { ToolCallTrace } from './ToolCallTrace';
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
              <div key={result.step_order}>
                <OutputCard
                  heading={<StepHeading result={result} />}
                  output={result.output}
                  input={result.input_used}
                  highlighted={focusedStep === result.step_order}
                />
                <ToolCallTrace calls={result.tool_calls ?? []} />
              </div>
            ))}
          </div>
          {position < stages.length - 1 && <StageArrow />}
        </div>
      ))}
    </div>
  );
}
