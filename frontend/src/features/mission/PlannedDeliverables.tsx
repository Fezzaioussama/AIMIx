import { BadgeCheck } from 'lucide-react';

import type { Pipeline, PipelineStep } from '../../core/api/types';
import { outputOrders, stepLabel } from '../pipelines/stages';
import { reviewerDefinition } from '../runs/report/reportModel';
import { reviewerNameAtStart } from '../runs/report/signOffCopy';

interface Planned {
  deliverables: PipelineStep[];
  /** The step that checks the work before it is handed over, if one does. */
  reviewer: PipelineStep | null;
}

/**
 * What a run of the team will hand over, as the run's report will show it: the output
 * steps, without the final check (the last step, by stage, with a review) unless it is
 * the only output, and then nothing checks it.
 */
function plannedOf(team: Pipeline): Planned {
  const outputs = outputOrders(team.steps);
  const made = team.steps.filter((step) => outputs.has(step.order));
  const reviewer = reviewerDefinition(team.steps);
  const others = made.filter((step) => step !== reviewer);
  return others.length > 0
    ? { deliverables: others, reviewer }
    : { deliverables: made, reviewer: null };
}

function PlannedItem({ step }: { step: PipelineStep }) {
  const expected = step.expected_output.trim();
  const role = step.role.trim();
  return (
    <li className="rounded-xl border border-dashed border-white/15 px-4 py-3">
      <p className="font-semibold text-pretty text-slate-100">{stepLabel(step)}</p>
      {expected && <p className="mt-0.5 text-sm text-pretty text-slate-300">{expected}</p>}
      {role && <p className="mt-1.5 text-xs text-slate-400">by {role}</p>}
    </li>
  );
}

/**
 * Before the first run: what the team will hand over, each deliverable named as its
 * document will be, and who checks the work first.
 */
export function PlannedDeliverables({ team }: { team: Pipeline | null }) {
  if (team === null) {
    return (
      <p className="text-sm text-pretty text-slate-300">
        Your results appear here once your team has worked on a mission.
      </p>
    );
  }
  const { deliverables, reviewer } = plannedOf(team);
  return (
    <section aria-label="Deliverables">
      <p className="mb-3 text-sm text-slate-300">
        When your team has run, you get {deliverables.length === 1 ? 'this' : 'these'}:
      </p>
      <ul className="space-y-2">
        {deliverables.map((step) => (
          <PlannedItem key={step.order} step={step} />
        ))}
      </ul>
      {reviewer && (
        <p className="mt-4 flex gap-2 text-sm text-pretty text-slate-300">
          <BadgeCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-sky-300" />
          {reviewerNameAtStart(reviewer)} checks the work before it reaches you.
        </p>
      )}
    </section>
  );
}
