import type { RunStep, StepResult } from '../../core/api/types';
import { CostText } from '../../core/ui/CostText';
import { describeCost, usageOfStep } from '../../core/usageFormat';
import { OutputBadge } from './GraphNodeCard';
import { modelLabel } from './modelLabel';
import { stepLabel } from './stages';

/**
 * Title row of a step's output card: name, position, model, output badge, and,
 * for a followed run's step, what its model calls cost.
 */
export function StepHeading({ result }: { result: StepResult | RunStep }) {
  const label = stepLabel({ order: result.step_order, title: result.title });
  const cost = 'input_tokens' in result ? describeCost(usageOfStep(result)) : null;
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
      {result.is_output && <OutputBadge />}
      {cost && <CostText view={cost} className="text-xs text-slate-300" />}
    </>
  );
}
