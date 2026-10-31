import type { RunStep, StepResult } from '../../core/api/types';
import { AiNotice } from '../../core/ui/AiNotice';
import { OutputCard } from './OutputCard';
import { StageArrow } from './StageArrow';
import { StageHeader } from './StageHeader';
import { StepHeading } from './StepHeading';
import { StepProgressCard } from './StepProgressCard';
import { ToolCallTrace } from './ToolCallTrace';
import { groupByStage } from './stages';

interface RunResultsProps {
  /** Finished results, or a followed run's steps — finished or not. */
  results: (StepResult | RunStep)[];
  focusedStep: number | null;
  /** Whether the followed run is still active: its pending steps are waiting, not skipped. */
  runActive?: boolean;
}

/** A followed run's step that has no output (yet). */
function inProgress(result: StepResult | RunStep): result is RunStep {
  return 'status' in result && result.status !== 'succeeded';
}

/** Every step's output, grouped by stage; parallel outputs sit side by side. */
export function RunResults({ results, focusedStep, runActive = false }: RunResultsProps) {
  const stages = groupByStage(results, (result) => result.stage);

  return (
    <div>
      {results.some((result) => !inProgress(result)) && <AiNotice className="mb-4" />}
      {stages.map((group, position) => (
        <div key={group.stage}>
          <StageHeader stage={group.stage} stepCount={group.items.length} />
          <div className={group.items.length > 1 ? 'grid gap-4 xl:grid-cols-2' : ''}>
            {group.items.map((result) => (
              <div key={result.step_order}>
                {inProgress(result) ? (
                  <StepProgressCard
                    step={result}
                    runActive={runActive}
                    highlighted={focusedStep === result.step_order}
                  />
                ) : (
                  <OutputCard
                    heading={<StepHeading result={result} />}
                    output={result.output}
                    input={result.input_used}
                    highlighted={focusedStep === result.step_order}
                  />
                )}
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
