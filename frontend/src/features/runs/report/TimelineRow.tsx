import {
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CirclePause,
  CircleX,
  Clock,
  Hand,
  LoaderCircle,
  type LucideIcon,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';

import type { Run, RunStep } from '../../../core/api/types';
import { useNow } from '../../../core/hooks/useNow';
import { RenderedMarkdown } from '../../../core/markdown/RenderedMarkdown';
import { CostText } from '../../../core/ui/CostText';
import { describeCost, usageOfStep } from '../../../core/usageFormat';
import { DisclosureButton, Foldable } from '../../pipelines/FoldablePanel';
import { NODE_STATUS_STYLES } from '../../pipelines/GraphNodeCard';
import { modelLabel } from '../../pipelines/modelLabel';
import { roundLabel } from '../../pipelines/roundNotes';
import { toolUsePhrase } from '../toolWords';
import { BottomHide } from './BottomHide';
import { useJump } from './jump';
import { definitionOf, reportIds, titleOf } from './reportModel';
import { roundOf } from './reviewRounds';
import { rowStatus, type RowIcon } from './stepCopy';
import { TEXT_LINK } from './textStyles';

/**
 * What a row's agent made: a deliverable, the check of the work, or work for the others;
 * `slot` for a deliverable not ready to read yet.
 */
export type RowRole = 'deliverable' | 'slot' | 'reviewer' | 'work';

/** Each row status's icon, in the diagram's colours (needsOk: amber, like the slot). */
const ROW_ICON: Record<RowIcon, { Icon: LucideIcon; className: string }> = {
  done: { Icon: CircleCheck, className: NODE_STATUS_STYLES.done.text },
  running: {
    Icon: LoaderCircle,
    className: `${NODE_STATUS_STYLES.running.text} motion-safe:animate-spin`,
  },
  waiting: { Icon: Clock, className: NODE_STATUS_STYLES.waiting.text },
  needsOk: { Icon: Hand, className: 'text-amber-300' },
  failed: { Icon: CircleX, className: NODE_STATUS_STYLES.failed.text },
  stopped: { Icon: CirclePause, className: NODE_STATUS_STYLES.stopped.text },
  skipped: { Icon: CircleMinus, className: NODE_STATUS_STYLES.skipped.text },
  pending: { Icon: CircleDashed, className: NODE_STATUS_STYLES.pending.text },
};

interface ActionProps {
  run: Run;
  step: RunStep;
  level: 2 | 3;
  onReadCheck: () => void;
}

/** "Read it above": up to the deliverable, its title taking the focus. */
function ReadAbove({ run, step }: ActionProps) {
  const jump = useJump();
  const ids = reportIds(run.id);
  const order = step.step_order;
  return (
    <a
      href={`#${ids.deliverable(order)}`}
      onClick={(event) => {
        event.preventDefault();
        jump(ids.deliverable(order), ids.title(order));
      }}
      className={`text-sm ${TEXT_LINK}`}
    >
      Read it above
    </a>
  );
}

/** "Read the check above": opens the sign-off's full check and goes to it. */
function ReadCheck({ run, onReadCheck }: ActionProps) {
  return (
    <a
      href={`#${reportIds(run.id).signOff}`}
      onClick={(event) => {
        event.preventDefault();
        onReadCheck();
      }}
      className={`text-sm ${TEXT_LINK}`}
    >
      Read the check above
    </a>
  );
}

/** Work only the team read: "Show what it wrote", folded under its row. */
function OwnOutput({ run, step, level }: ActionProps) {
  const [open, setOpen] = useState(false);
  const rowId = reportIds(run.id).agent(step.step_order);
  const bodyId = `${rowId}-output`;
  const toggleId = `${rowId}-toggle`;
  return (
    <>
      <DisclosureButton
        open={open}
        controls={bodyId}
        label={open ? 'Hide what it wrote' : 'Show what it wrote'}
        onToggle={() => setOpen((shown) => !shown)}
        id={toggleId}
      />
      <Foldable id={bodyId} open={open} size="small" bodyClassName="pt-2">
        <RenderedMarkdown
          markdown={step.output}
          headingBase={level + 2}
          className="text-slate-200"
        />
        <BottomHide
          text={step.output}
          label="Hide what it wrote"
          targetId={toggleId}
          toggleId={toggleId}
          onClose={() => setOpen(false)}
        />
      </Foldable>
    </>
  );
}

/** The way from a row to its agent's text, by what the agent made (Strategy + Registry). */
const ROW_ACTION: Record<RowRole, (props: ActionProps) => ReactNode> = {
  deliverable: ReadAbove,
  slot: () => null,
  reviewer: ReadCheck,
  work: OwnOutput,
};

/** "Model: Sonnet 4.5 · Round 2 of 3". */
function facts(step: RunStep, run: Run): string {
  const lines = [`Model: ${modelLabel(step.model)}`];
  if (step.rounds > 1) lines.push(roundLabel(step.rounds, roundOf(step, run).total));
  return lines.join(' · ');
}

interface TimelineRowProps {
  run: Run;
  step: RunStep;
  role: RowRole;
  level: 2 | 3;
  /** Opens the sign-off's full check and goes to it (the reviewer's row). */
  onReadCheck: () => void;
}

/**
 * One agent in "How your team got there": where it is and what it took, its model and
 * round, the tools it used, and a way to its text, which is shown once on the page.
 */
export function TimelineRow({ run, step, role, level, onReadCheck }: TimelineRowProps) {
  const now = useNow(step.status === 'running');
  const status = rowStatus(step, run, now);
  const icon = ROW_ICON[status.icon];
  const cost = describeCost(usageOfStep(step));
  const title = titleOf(step);
  const agent = definitionOf(run, step).role.trim();
  const tools = toolUsePhrase(step.tool_calls);
  const Action = ROW_ACTION[role];
  return (
    <li
      id={reportIds(run.id).agent(step.step_order)}
      className="grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-3 py-3"
    >
      <icon.Icon aria-hidden="true" className={`mt-0.5 size-4 ${icon.className}`} />
      <div>
        <p className="text-sm font-medium break-words text-slate-100">
          {title}
          {agent && agent.toLowerCase() !== title.toLowerCase() && (
            <span className="font-normal text-slate-400"> · by {agent}</span>
          )}
        </p>
        <p className="mt-0.5 text-sm text-slate-300 tabular-nums">
          {status.words}
          {cost && (
            <>
              {' · '}
              <CostText view={cost} />
            </>
          )}
        </p>
        <p className="mt-0.5 text-xs text-slate-400">{facts(step, run)}</p>
        {tools && <p className="mt-0.5 text-xs text-slate-400">{tools}</p>}
        {step.output.trim() !== '' && (
          <div className="mt-1">
            <Action run={run} step={step} level={level} onReadCheck={onReadCheck} />
          </div>
        )}
      </div>
    </li>
  );
}
