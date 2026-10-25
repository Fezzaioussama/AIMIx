import type { RunSummary } from '../../core/api/types';
import { CostText } from '../../core/ui/CostText';
import { describeCost } from '../../core/usageFormat';
import { limitParts } from './runBudget';

interface RunCostProps {
  run: RunSummary;
  /** Still queued or running: no usage yet is normal, not a gap. */
  active: boolean;
}

/** What the run's model calls cost so far, next to its spending limit when it has one. */
export function RunCost({ run, active }: RunCostProps) {
  const view = describeCost(run.usage);
  const limit = limitParts(run).join(' or ');
  if (view === null) {
    if (active) return limit ? <span className="text-slate-400">Limit {limit}</span> : null;
    return <span className="text-slate-400">No usage recorded</span>;
  }
  return (
    <span className="flex items-baseline gap-1.5">
      <CostText view={view} className="text-slate-200" />
      {limit && <span className="text-slate-400">of {limit} limit</span>}
    </span>
  );
}
