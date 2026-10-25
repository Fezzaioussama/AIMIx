import { Link } from 'react-router-dom';

import type { Run } from '../../core/api/types';
import { formatDateTime } from '../../core/time';
import { RunTriggerTag } from './RunTriggerTag';

/**
 * "Started Oct 24, 9:58 PM · Scheduled · Open the pipeline": when a run began, what started
 * it (marked only when a schedule did), and the way back to its pipeline while it exists.
 */
export function RunByline({ run }: { run: Run }) {
  return (
    <p className="mt-1 text-sm text-slate-400">
      Started {formatDateTime(run.started_at ?? run.created_at)}
      {run.trigger === 'schedule' && (
        <>
          {' · '}
          <RunTriggerTag trigger={run.trigger} />
        </>
      )}
      {run.pipeline_id !== null && (
        <>
          {' · '}
          <Link
            to="/pipeline"
            state={{ pipelineId: run.pipeline_id }}
            className="text-sky-300 underline-offset-2 hover:underline"
          >
            Open the pipeline
          </Link>
        </>
      )}
    </p>
  );
}
