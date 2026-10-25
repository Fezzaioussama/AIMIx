import type { RunStep, StepResult } from '../../core/api/types';
import { CostText } from '../../core/ui/CostText';
import { describeCost, usageOfStep } from '../../core/usageFormat';
import { OutputBadge } from './GraphNodeCard';
import { modelLabel } from './modelLabel';
import { useRunFlow } from './RunFlowContext';
import { reviewNote, roundLabel } from './roundNotes';
import { stepLabel } from './stages';
import { roundTotals } from './stepFlow';

/** What a followed run's step went through in review loops: its round, and a reviewer's outcome. */
function ReviewFacts({ step }: { step: RunStep }) {
  const { steps } = useRunFlow();
  const review = steps.find((item) => item.order === step.step_order)?.review ?? null;
  const total = roundTotals(steps).get(step.step_order) ?? null;
  // A reviewer's outcome is told once it has answered; a running step has none yet.
  const note =
    review !== null && step.status === 'succeeded' ? reviewNote(step, review.max_rounds) : null;
  return (
    <>
      {step.rounds > 1 && (
        <span className="rounded-md bg-sky-400/15 px-2 py-1 text-xs font-semibold text-sky-200">
          {roundLabel(step.rounds, total)}
        </span>
      )}
      {note && <span className="text-xs text-slate-300">{note}</span>}
    </>
  );
}

/**
 * Title row of a step's output card: name, position, model, output badge, and,
 * for a followed run's step, what its model calls cost and how many review rounds it
 * went through.
 */
export function StepHeading({ result }: { result: StepResult | RunStep }) {
  const label = stepLabel({ order: result.step_order, title: result.title });
  const followed = 'input_tokens' in result;
  const cost = followed ? describeCost(usageOfStep(result)) : null;
  // A step that was skipped is never one of the pipeline's outputs.
  const skipped = followed && result.status === 'skipped';
  return (
    <>
      <span className="font-semibold text-slate-100">{label}</span>
      {result.title.trim() && (
        <span className="rounded-md bg-sky-400/15 px-2 py-1 text-xs font-semibold text-sky-400">
          #{result.step_order}
        </span>
      )}
      <span className="rounded-md bg-white/5 px-2 py-1 text-xs text-slate-400">
        {modelLabel(result.model)}
      </span>
      {result.is_output && !skipped && <OutputBadge />}
      {followed && <ReviewFacts step={result} />}
      {cost && <CostText view={cost} className="text-xs text-slate-300" />}
    </>
  );
}
