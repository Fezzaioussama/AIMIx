import { useId, type ReactNode } from 'react';

import type { PipelineInput, PipelineStep, StepCondition, StepReview } from '../../core/api/types';
import { FIELD, INLINE_FIELD, SMALL_ACTION } from './fieldStyles';
import {
  CONDITION_OPERATORS,
  CONDITION_VALUE_MAX_LENGTH,
  REVIEW_MAX_ROUNDS,
  conditionSources,
  describeCondition,
  describeReview,
  earlierStages,
  newCondition,
  newReview,
  operatorOption,
  timesWords,
  type SourceOption,
} from './stepFlow';
import { conditionProblem, reviewProblem } from './stepFlowProblems';
import { stepLabel } from './stages';

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

function Problem({ id, text }: { id: string; text: string | null }) {
  if (text === null) return null;
  return (
    <p id={id} className="text-[11px] text-amber-300">
      {text}
    </p>
  );
}

function Labelled({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-slate-400">
        {label}
      </label>
      {children}
    </div>
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

interface ConditionFieldsProps {
  step: PipelineStep;
  condition: StepCondition;
  sources: SourceOption[];
  problem: string | null;
  onChange: (condition: StepCondition | null) => void;
}

/** The sources on offer, plus the one the condition points at when it is no longer there. */
function withStale(sources: SourceOption[], source: string): SourceOption[] {
  if (sources.some((option) => option.value === source)) return sources;
  return [{ value: source, label: 'Not available any more' }, ...sources];
}

interface FieldProps {
  id: string;
  condition: StepCondition;
  onChange: (condition: StepCondition) => void;
  /** The id of the problem text, while there is one. */
  described?: string;
}

function SourceField({
  id,
  condition,
  onChange,
  described,
  sources,
}: FieldProps & { sources: SourceOption[] }) {
  return (
    <Labelled id={id} label="What to look at">
      <select
        id={id}
        value={condition.source}
        aria-describedby={described}
        aria-invalid={described !== undefined}
        onChange={(event) => onChange({ ...condition, source: event.target.value })}
        className={FIELD}
      >
        {withStale(sources, condition.source).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Labelled>
  );
}

function OperatorField({ id, condition, onChange }: FieldProps) {
  function choose(value: string) {
    const next = operatorOption(value);
    if (next === undefined) return;
    onChange({ ...condition, operator: next.value, value: next.takesValue ? condition.value : '' });
  }
  return (
    <Labelled id={id} label="Check whether it">
      <select
        id={id}
        value={condition.operator}
        onChange={(event) => choose(event.target.value)}
        className={FIELD}
      >
        {CONDITION_OPERATORS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Labelled>
  );
}

function ValueField({ id, condition, onChange, described }: FieldProps) {
  return (
    <Labelled id={id} label="Text to compare with">
      <input
        id={id}
        type="text"
        value={condition.value}
        maxLength={CONDITION_VALUE_MAX_LENGTH}
        placeholder="e.g. blog"
        aria-describedby={described}
        onChange={(event) => onChange({ ...condition, value: event.target.value })}
        className={FIELD}
      />
    </Labelled>
  );
}

function ConditionFields({ step, condition, sources, problem, onChange }: ConditionFieldsProps) {
  const id = useId();
  const described = problem === null ? undefined : `${id}-problem`;
  const field = { condition, onChange, described };
  return (
    <>
      <div className="space-y-2">
        <SourceField id={`${id}-source`} sources={sources} {...field} />
        <OperatorField id={`${id}-operator`} {...field} />
        {operatorOption(condition.operator)?.takesValue !== false && (
          <ValueField id={`${id}-value`} {...field} />
        )}
      </div>
      <p className="text-slate-400">
        Capital letters and spaces around the text do not matter. When it does not hold, “
        {stepLabel(step)}” is skipped.
      </p>
      <Problem id={`${id}-problem`} text={problem} />
      <button type="button" onClick={() => onChange(null)} className={SMALL_ACTION}>
        Remove the condition
      </button>
    </>
  );
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

interface ReviewFieldsProps {
  step: PipelineStep;
  steps: PipelineStep[];
  review: StepReview;
  onChange: (review: StepReview | null) => void;
}

function ReviewFields({ step, steps, review, onChange }: ReviewFieldsProps) {
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
