import { BusyNotice } from '../../core/ui/BusyNotice';
import { DeleteRunButton } from './DeleteRunButton';
import { RunByline } from './RunByline';
import { RunReport } from './report/RunReport';
import { isActive } from './runStatus';
import type { LiveRunState } from './useRun';

interface RunDetailProps {
  live: LiveRunState;
  onDelete: () => void;
  deleting: boolean;
}

/**
 * One run from the history: its pipeline's name (an h2 under the page's "Runs"), which run
 * it is, then its report, with the team's diagram in the report's appendix.
 */
export function RunDetail({ live, onDelete, deleting }: RunDetailProps) {
  const { run } = live;
  if (run === null) {
    return live.error ? (
      <p role="alert" className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-300">
        {live.error}
      </p>
    ) : (
      <BusyNotice className="mt-12">Loading the run…</BusyNotice>
    );
  }
  return (
    <article aria-labelledby="run-title">
      <header className="mb-8">
        <h2 id="run-title" className="text-2xl font-bold tracking-tight break-words">
          {run.pipeline_name}
        </h2>
        <RunByline run={run} />
      </header>
      <RunReport
        key={run.id}
        run={run}
        control={live}
        level={3}
        extras={{
          diagram: true,
          actions: isActive(run.status) ? undefined : (
            <DeleteRunButton onDelete={onDelete} busy={deleting} />
          ),
        }}
      />
    </article>
  );
}
