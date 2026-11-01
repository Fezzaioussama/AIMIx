import { Link } from 'react-router-dom';

import type { Run } from '../../core/api/types';
import { formatDateTime } from '../../core/time';
import { FOCUS_RING } from '../../core/ui/focus';
import { hasTriggerTag, RunTriggerTag } from './RunTriggerTag';

/**
 * "Run #4 · Started Oct 24, 9:58 PM · Scheduled · Open the pipeline": which run it is, when
 * it began, what started it (marked only when a schedule or a webhook did), and the way back
 * to its pipeline while it exists.
 */
export function RunByline({ run }: { run: Run }) {
  return (
    <p className="mt-1 text-sm text-slate-400">
      Run #{run.id} · Started {formatDateTime(run.started_at ?? run.created_at)}
      {hasTriggerTag(run.trigger) && (
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
            className={`rounded-sm text-sky-300 underline-offset-2 hover:underline ${FOCUS_RING}`}
          >
            Open the pipeline
          </Link>
        </>
      )}
    </p>
  );
}
