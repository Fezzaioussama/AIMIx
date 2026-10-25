import { useId } from 'react';

import type { PipelineStep, StepCondition } from '../../core/api/types';
import { Labelled, Problem } from './FlowFieldParts';
import { FIELD, SMALL_ACTION } from './fieldStyles';
import { stepLabel } from './stages';
import {
  CONDITION_OPERATORS,
  CONDITION_VALUE_MAX_LENGTH,
  operatorOption,
  type SourceOption,
} from './stepFlow';

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

/** The three fields of a condition, what it does, what is wrong with it and its removal. */
export function ConditionFields({
  step,
  condition,
  sources,
  problem,
  onChange,
}: ConditionFieldsProps) {
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
