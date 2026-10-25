import { Link } from 'react-router-dom';

import type { Run, RunStatus } from '../../core/api/types';
import { stepLabel } from '../pipelines/stages';
import { RUN_STATUS_STYLES, RunStatusBadge } from '../runs/RunStatusBadge';
import { ANSWER_ACTION, Bubble } from './Bubble';
import type { ViewProps } from './messageContext';
import { countOf } from './teamBrief';

function readyLine(run: Run): string {
  const ready = run.steps.filter((step) => step.status === 'succeeded' && step.is_output).length;
  if (ready === 0) return 'Done. Every step finished; see Results.';
  return `Done! ${countOf(ready, 'deliverable')} ${ready === 1 ? 'is' : 'are'} ready under Results.`;
}

function failedLine(run: Run): string {
  const failed = run.steps.find((step) => step.status === 'failed');
  const what = failed ? `“${stepLabel({ order: failed.step_order, title: failed.title })}”` : 'A step';
  return `The run stopped: ${what} failed. You can resume it under Results.`;
}

/** What AIMIx says about a run, by status; a status added later reads as its badge word. */
const RUN_LINES: Partial<Record<RunStatus, (run: Run) => string>> = {
  queued: () => 'Your team is lined up and starts as soon as a slot is free.',
  running: () => 'Your team is on it. Each result appears under Results as soon as it is ready.',
  succeeded: readyLine,
  failed: failedLine,
  cancelled: () => 'You stopped this run. You can resume it under Results.',
  interrupted: () => 'The run was interrupted. You can resume it under Results.',
};

function runLine(run: Run): string {
  return RUN_LINES[run.status]?.(run) ?? `Run: ${RUN_STATUS_STYLES[run.status].label}.`;
}

/** A run started from the conversation: live while it is the mission's newest run. */
export function RunMessageView({ message, context }: ViewProps<'run'>) {
  const run = context.latestRun?.id === message.runId ? context.latestRun : null;
  if (run === null) {
    return (
      <Bubble>
        Run #{message.runId}.{' '}
        <Link to={`/runs/${message.runId}`} className={ANSWER_ACTION}>
          Open it in Runs
        </Link>
      </Bubble>
    );
  }
  return (
    <Bubble>
      <div className="flex flex-wrap items-center gap-2">
        <RunStatusBadge status={run.status} />
        <span>{runLine(run)}</span>
      </div>
      <button
        type="button"
        onClick={() => context.showPane('results')}
        className={`mt-2 ${ANSWER_ACTION}`}
      >
        See results
      </button>
    </Bubble>
  );
}
