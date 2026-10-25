import type { ReactNode } from 'react';

import type { PipelineInput, PipelineStep } from '../../core/api/types';
import { ConditionFields } from './ConditionFields';
import { ReviewFields } from './ReviewFields';
import { SMALL_ACTION } from './fieldStyles';
import {
  conditionSources,
  describeCondition,
  describeReview,
  earlierStages,
  newCondition,
  newReview,
} from './stepFlow';
import { conditionProblem } from './stepFlowProblems';

interface StepFlowFieldsProps {
  step: PipelineStep;
  /** Every step of the pipeline: what a condition may look at, where a review may send work. */
  steps: PipelineStep[];
  inputs: PipelineInput[];
  onChange: (patch: Partial<PipelineStep>) => void;
}

/**
 * Two options that change how work flows, each folded away until wanted: "Run this step
 * only if…" and, for a step that has an earlier stage to send work to, "Review loop".
 */
export function StepFlowFields(props: StepFlowFieldsProps) {
  const { step, steps } = props;
  const canReview = earlierStages(step, steps).length > 0 || step.review !== null;
  return (
    <div className="mt-3 space-y-2">
      <ConditionSection {...props} />
      {canReview && <ReviewSection {...props} />}
    </div>
  );
}

interface FlowSectionProps {
  title: string;
  /** What is set, in a few words after the title; null when nothing is. */
  summary: string | null;
  children: ReactNode;
}

function FlowSection({ title, summary, children }: FlowSectionProps) {
  return (
    <details className="rounded-md border border-white/10 bg-slate-900/50 px-2 py-1.5 text-xs">
      <summary className="cursor-pointer text-slate-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
        <span className="font-medium">{title}</span>
        {summary && <span className="text-sky-300"> · {summary}</span>}
      </summary>
      <div className="mt-2 space-y-2">{children}</div>
    </details>
  );
}

function ConditionSection({ step, steps, inputs, onChange }: StepFlowFieldsProps) {
  const described = describeCondition(step, steps, inputs);
  return (
    <FlowSection title="Run this step only if…" summary={described}>
      {step.condition === null ? (
        <>
          <p className="text-slate-400">This step always runs.</p>
          <button
            type="button"
            onClick={() => onChange({ condition: newCondition() })}
            className={SMALL_ACTION}
          >
            Add a condition
          </button>
        </>
      ) : (
        <ConditionFields
          step={step}
          condition={step.condition}
          sources={conditionSources(step, steps, inputs)}
          problem={conditionProblem(step, steps, inputs)}
          onChange={(condition) => onChange({ condition })}
        />
      )}
    </FlowSection>
  );
}

function ReviewSection({ step, steps, onChange }: StepFlowFieldsProps) {
  const { review } = step;
  return (
    <FlowSection title="Review loop" summary={review && describeReview(review)}>
      {review === null ? (
        <>
          <p className="text-slate-400">This step does not send work back.</p>
          <button
            type="button"
            onClick={() => onChange({ review: newReview(step, steps) })}
            className={SMALL_ACTION}
          >
            Make this step a reviewer
          </button>
        </>
      ) : (
        <ReviewFields
          step={step}
          steps={steps}
          review={review}
          onChange={(next) => onChange({ review: next })}
        />
      )}
    </FlowSection>
  );
}
