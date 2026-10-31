import type { PipelineStep, RunStep } from '../../core/api/types';
import { NODE_STATUS_STYLES } from '../pipelines/GraphNodeCard';
import { liveNodeStatus, type NodeStatus } from '../pipelines/pipelineGraph';
import { reviewNote, roundLabel } from '../pipelines/roundNotes';
import { groupByStage, outputOrders, stepLabel } from '../pipelines/stages';
import { roundTotals } from '../pipelines/stepFlow';

interface TeamRosterProps {
  steps: PipelineStep[];
  /** The followed run's steps, when there is one: each agent's live status and work. */
  liveSteps?: RunStep[];
  runActive: boolean;
  /** The agent the edit drawer is open on. */
  selected: number | null;
  /** Opens an agent for editing; missing while the team cannot be edited. */
  onEditStep?: (order: number) => void;
}

/** The first words of an agent's work, as plain text, for its card. */
const PREVIEW_CHARS = 160;

export function preview(output: string): string {
  const text = output
    .replace(/[#*_`>|]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS).trimEnd()}…` : text;
}

interface AgentCardProps {
  step: PipelineStep;
  live: RunStep | undefined;
  status: NodeStatus;
  deliverable: boolean;
  roundTotal: number | null;
  selected: boolean;
  onEdit?: () => void;
}

/** What the card says under the agent's name: its status, its round, a reviewer's outcome. */
function statusLine({ step, live, status, roundTotal }: AgentCardProps): string {
  const parts = [NODE_STATUS_STYLES[status].label];
  if (live && live.rounds > 1) parts.push(roundLabel(live.rounds, roundTotal));
  const note =
    step.review && live?.status === 'succeeded' ? reviewNote(live, step.review.max_rounds) : null;
  if (note) parts.push(note);
  return parts.join(' · ');
}

function AgentCard(props: AgentCardProps) {
  const { step, live, status, deliverable, selected, onEdit } = props;
  const style = NODE_STATUS_STYLES[status];
  const name = step.role.trim() || stepLabel(step);
  const work = status === 'done' && live ? preview(live.output) : '';
  const body = (
    <>
      <span
        aria-hidden="true"
        className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400/80 via-indigo-500/80 to-purple-500/80 text-sm font-semibold text-white uppercase"
      >
        {name.charAt(0)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold text-slate-50">{name}</span>
          {deliverable && (
            <span className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-amber-300 uppercase">
              Deliverable
            </span>
          )}
          {step.review && (
            <span className="rounded bg-purple-400/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-purple-200 uppercase">
              Checks the work
            </span>
          )}
        </span>
        {step.title.trim() && step.title.trim() !== name && (
          <span className="mt-0.5 block text-sm text-slate-300">{step.title.trim()}</span>
        )}
        <span className={`mt-1.5 flex items-center gap-1.5 text-xs ${style.text}`}>
          <span
            aria-hidden="true"
            className={`size-1.5 shrink-0 rounded-full ${style.dot} ${status === 'running' ? 'motion-safe:animate-pulse' : ''}`}
          />
          {statusLine(props)}
        </span>
        {work && <span className="mt-1.5 line-clamp-2 block text-sm text-slate-400">{work}</span>}
      </span>
    </>
  );
  // Read out as one line: what it makes, who makes it, whether it is a deliverable, how it is doing.
  const label = `${stepLabel(step)}, ${name}, ${deliverable ? 'deliverable' : 'intermediate'}, ${statusLine(props)}`;
  const frame = `flex w-full items-start gap-3 rounded-xl border bg-slate-900/70 p-3 text-left ${style.border} ${
    selected ? 'ring-2 ring-sky-400' : ''
  }`;
  if (!onEdit) {
    return (
      <div role="group" aria-label={label} className={frame}>
        {body}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onEdit}
      aria-label={label}
      className={`${frame} transition-colors hover:bg-slate-800/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400`}
    >
      {body}
    </button>
  );
}

/**
 * The team as people: every agent by stage, in the order they work, with its role, what
 * it makes, its live status during a run, and the start of its work once done. Agents of
 * one stage work at the same time. Selecting an agent opens it for editing.
 */
export function TeamRoster({ steps, liveSteps, runActive, selected, onEditStep }: TeamRosterProps) {
  const deliverables = outputOrders(steps);
  const totals = roundTotals(steps);
  const live = new Map((liveSteps ?? []).map((step) => [step.step_order, step]));
  return (
    <ol aria-label="Your team" className="space-y-4">
      {groupByStage(steps, (step) => step.stage).map((group, index) => (
        <li key={group.stage}>
          <p className="mb-2 text-[11px] font-semibold tracking-widest text-slate-400 uppercase">
            Step {index + 1}
            {group.items.length > 1 && ' · together'}
          </p>
          <ul className="space-y-2">
            {group.items.map((step) => {
              const run = live.get(step.order);
              return (
                <li key={step.order}>
                  <AgentCard
                    step={step}
                    live={run}
                    status={run ? liveNodeStatus(run, runActive) : 'pending'}
                    deliverable={deliverables.has(step.order)}
                    roundTotal={totals.get(step.order) ?? null}
                    selected={selected === step.order}
                    onEdit={onEditStep && (() => onEditStep(step.order))}
                  />
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
