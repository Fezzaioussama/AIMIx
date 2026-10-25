import { useId } from 'react';

import type { PipelineStep, StepReview } from '../../core/api/types';
import { Problem } from './FlowFieldParts';
import { INLINE_FIELD, SMALL_ACTION } from './fieldStyles';
import { stepLabel } from './stages';
import { REVIEW_MAX_ROUNDS, earlierStages, timesWords } from './stepFlow';
import { reviewProblem } from './stepFlowProblems';

interface ReviewFieldsProps {
  step: PipelineStep;
  steps: PipelineStep[];
  review: StepReview;
  onChange: (review: StepReview | null) => void;
}

/** The stages a review may send work to, each with the names of its steps. */
function stageOptions(step: PipelineStep, steps: PipelineStep[], chosen: number) {
  const stages = earlierStages(step, steps);
  const all = stages.includes(chosen) ? stages : [chosen, ...stages];
  return all.map((stage) => {
    const names = steps
      .filter((other) => other.stage === stage)
      .map(stepLabel)
      .join(', ');
    return { stage, label: names ? `${stage} · ${names}` : `${stage}` };
  });
}

/** The two choices of a review loop, what the prompt should do, what is wrong and its removal. */
export function ReviewFields({ step, steps, review, onChange }: ReviewFieldsProps) {
  const id = useId();
  const problem = reviewProblem(step, steps);
  return (
    <>
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5 text-slate-300">
        Send the work back to stage
        <select
          aria-label="Send the work back to stage"
          value={review.send_back_to_stage}
          aria-describedby={problem === null ? undefined : `${id}-problem`}
          aria-invalid={problem !== null}
          onChange={(event) =>
            onChange({ ...review, send_back_to_stage: Number(event.target.value) })
          }
          className={INLINE_FIELD}
        >
          {stageOptions(step, steps, review.send_back_to_stage).map((option) => (
            <option key={option.stage} value={option.stage}>
              {option.label}
            </option>
          ))}
        </select>
        up to
        <select
          aria-label="Most times to send the work back"
          value={review.max_rounds}
          onChange={(event) => onChange({ ...review, max_rounds: Number(event.target.value) })}
          className={INLINE_FIELD}
        >
          {Array.from({ length: REVIEW_MAX_ROUNDS }, (_, index) => index + 1).map((times) => (
            <option key={times} value={times}>
              {timesWords(times)}
            </option>
          ))}
        </select>
        when this step says the work needs fixes.
      </p>
      <p className="text-slate-400">
        Write this step’s prompt so it judges the work it receives and says what to fix. AIMIx asks
        for the verdict itself.
      </p>
      <Problem id={`${id}-problem`} text={problem} />
      <button type="button" onClick={() => onChange(null)} className={SMALL_ACTION}>
        Remove the review loop
      </button>
    </>
  );
}
