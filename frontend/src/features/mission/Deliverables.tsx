import type { Pipeline, Run, RunStep } from '../../core/api/types';
import { OutputCard } from '../pipelines/OutputCard';
import { stepLabel } from '../pipelines/stages';
import { StepHeading } from '../pipelines/StepHeading';
import { isActive } from '../runs/runStatus';
import { describeTeam } from './teamBrief';

interface DeliverablesProps {
  /** The mission's newest run; null before it has run. */
  run: Run | null;
  /** The team on screen, for what to expect before a run. */
  team: Pipeline | null;
}

function names(steps: RunStep[]): string {
  return steps.map((step) => `“${stepLabel({ order: step.step_order, title: step.title })}”`).join(', ');
}

/** Before a run: what each deliverable will be, as the plan says. */
function Planned({ team }: { team: Pipeline }) {
  const planned = describeTeam(team).agents.filter((agent) => agent.deliverable);
  return (
    <>
      <p className="mb-3 text-sm text-slate-300">
        When your team has run, you get {planned.length === 1 ? 'this' : 'these'}:
      </p>
      <ul className="space-y-2">
        {planned.map((agent) => (
          <li
            key={agent.order}
            className="rounded-xl border border-dashed border-white/15 px-3 py-2.5 text-sm"
          >
            <p className="font-semibold text-slate-100">{agent.name}</p>
            <p className="text-slate-300">{agent.task}</p>
          </li>
        ))}
      </ul>
    </>
  );
}

/** The run's output steps: each as a card once it is ready, the rest named. */
function Ready({ run }: { run: Run }) {
  const outputs = run.steps.filter((step) => step.is_output);
  const ready = outputs
    .filter((step) => step.status === 'succeeded')
    .sort((a, b) => a.stage - b.stage || a.step_order - b.step_order);
  const waiting = outputs.filter((step) => step.status !== 'succeeded');

  return (
    <>
      {ready.length === 0 && (
        <p className="text-sm text-slate-300">
          Each deliverable appears here as soon as its agent has finished.
        </p>
      )}
      <div className="space-y-4">
        {ready.map((step) => (
          <OutputCard
            key={step.step_order}
            heading={<StepHeading result={step} />}
            output={step.output}
            foldable={ready.length > 1}
          />
        ))}
      </div>
      {waiting.length > 0 && ready.length > 0 && (
        <p className="mt-3 text-sm text-slate-300">
          {isActive(run.status) ? 'Still working on' : 'Not finished'}: {names(waiting)}.
        </p>
      )}
    </>
  );
}

/**
 * What the mission delivers, prominently: the finished output steps of its newest run
 * as readable cards (copy, raw view), or what to expect before there is a run.
 */
export function Deliverables({ run, team }: DeliverablesProps) {
  return (
    <section aria-labelledby="mission-deliverables">
      <h3 id="mission-deliverables" className="mb-3 text-base font-semibold text-white">
        Deliverables
      </h3>
      {run !== null && <Ready run={run} />}
      {run === null && team !== null && <Planned team={team} />}
      {run === null && team === null && (
        <p className="text-sm text-slate-300">
          Your results appear here once your team has worked on a mission.
        </p>
      )}
    </section>
  );
}
