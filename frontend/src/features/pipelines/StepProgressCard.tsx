import { useEffect, useRef } from 'react';

import type { RunStep } from '../../core/api/types';
import { useNow } from '../../core/hooks/useNow';
import { elapsedMs, formatDuration } from '../../core/time';
import { Spinner } from '../../core/ui/Spinner';
import { NODE_STATUS_STYLES, SKIPPED_REASON } from './GraphNodeCard';
import { liveNodeStatus, type NodeStatus } from './pipelineGraph';
import { useRunFlow } from './RunFlowContext';
import { StepHeading } from './StepHeading';
import { describeCondition } from './stepFlow';

/** What a step without an output is doing, in plain words. */
const STATUS_TEXT: Record<Exclude<NodeStatus, 'done'>, string> = {
  pending: 'Did not run.',
  waiting: 'Waiting for the steps before it.',
  running: 'Working on it…',
  failed: 'This step failed.',
  stopped: 'Stopped before it finished.',
  skipped: `Skipped. ${SKIPPED_REASON}.`,
};

/** For a skipped step: the condition that was not met, as the pipeline defines it. */
function SkippedCondition({ step }: { step: RunStep }) {
  const { steps, inputs } = useRunFlow();
  const definition = steps.find((item) => item.order === step.step_order);
  const described = definition ? describeCondition(definition, steps, inputs) : null;
  return described === null ? null : <> It runs only if {described}.</>;
}

interface StepProgressCardProps {
  step: RunStep;
  runActive: boolean;
  highlighted?: boolean;
}

/** A run's step that has no output yet, or never will: its status, time and error. */
export function StepProgressCard({ step, runActive, highlighted = false }: StepProgressCardProps) {
  const status = liveNodeStatus(step, runActive);
  const style = NODE_STATUS_STYLES[status];
  const now = useNow(step.status === 'running');
  const elapsed = elapsedMs(step.started_at, step.finished_at, now);
  const card = useRef<HTMLDivElement>(null);

  // Bring the card into view when the diagram points at it.
  useEffect(() => {
    if (highlighted) card.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [highlighted]);

  return (
    <div
      ref={card}
      className={`min-w-0 scroll-mt-6 rounded-2xl border bg-slate-800/30 p-6 ${
        highlighted ? 'border-sky-400/60 ring-2 ring-sky-400/40' : style.border
      }`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <StepHeading result={step} />
        <span className={`flex items-center gap-1.5 text-xs font-medium ${style.text}`}>
          {status === 'running' ? (
            <Spinner decorative className="size-3" />
          ) : (
            <span className={`size-2 rounded-full ${style.dot}`} aria-hidden="true" />
          )}
          {style.label}
        </span>
        {elapsed !== null && (
          <span className="text-xs text-slate-400">{formatDuration(elapsed)}</span>
        )}
      </div>
      {status !== 'done' && (
        <p className="text-sm text-slate-300">
          {STATUS_TEXT[status]}
          {status === 'skipped' && <SkippedCondition step={step} />}
        </p>
      )}
      {step.error && (
        <p className="mt-2 rounded-lg bg-red-500/10 px-3 py-2 text-sm break-words text-red-300">
          {step.error.detail}
        </p>
      )}
    </div>
  );
}
