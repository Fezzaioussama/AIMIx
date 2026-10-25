import type { ReactNode } from 'react';

import type { Run, RunBudget } from '../../core/api/types';
import { elapsedMs } from '../../core/time';
import { PipelineRunView } from '../pipelines/PipelineRunView';
import { LiveRunHeader } from './LiveRunHeader';
import { isActive } from './runStatus';

export interface LiveRunProps {
  /** The run to show, e.g. `useRun(id).run`; pass each new poll. */
  run: Run;
  onStop?: () => void;
  /** Continue the run; one that stopped at its spending limit passes a higher limit. */
  onResume?: (budget?: RunBudget) => void;
  /** A stop or resume is in flight. */
  busy?: boolean;
  /** Why the last fetch, stop or resume failed. */
  error?: string;
  /** More controls next to Stop and Resume (e.g. Delete). */
  actions?: ReactNode;
  /** Shown under the status bar, before the results (e.g. the run's inputs). */
  children?: ReactNode;
}

/**
 * One run, live: the pipeline it ran (its own snapshot) with each step's
 * status on the diagram, a status bar with Stop and Resume, and every step's
 * output, tool use, time and error as soon as they are saved. Embeddable
 * anywhere: pair it with `useRun(runId)`, which polls while the run is active.
 */
export function LiveRun({ run, onStop, onResume, busy, error, actions, children }: LiveRunProps) {
  const active = isActive(run.status);
  return (
    <PipelineRunView
      steps={run.definition.steps}
      inputs={run.definition.inputs}
      liveSteps={run.steps}
      runKey={run.id}
      isRunning={active}
      input={run.input}
      elapsedMs={active ? null : elapsedMs(run.started_at, run.finished_at, Date.now())}
    >
      <LiveRunHeader
        run={run}
        onStop={onStop}
        onResume={onResume}
        busy={busy}
        error={error}
        actions={actions}
      />
      {children}
    </PipelineRunView>
  );
}
