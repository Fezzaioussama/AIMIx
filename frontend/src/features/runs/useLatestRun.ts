import { useCallback, useEffect, useState } from 'react';

import { listRuns } from '../../core/api/runs';
import type { Run } from '../../core/api/types';
import { useRun, type LiveRunState } from './useRun';

interface Latest {
  pipelineId: number;
  runId: number;
}

export interface LatestRunState extends LiveRunState {
  /** Follow a run just started here instead. */
  follow: (run: Run) => void;
}

/**
 * The newest run of a pipeline, followed live (`useRun`): loaded when the
 * pipeline opens, so a run started earlier — even before leaving the page —
 * shows again, and replaced by each run started here.
 */
export function useLatestRun(pipelineId: number | undefined): LatestRunState {
  const [latest, setLatest] = useState<Latest | null>(null);
  const runId = latest !== null && latest.pipelineId === pipelineId ? latest.runId : null;
  const live = useRun(runId);
  const { adopt } = live;

  useEffect(() => {
    if (pipelineId === undefined) return;
    const controller = new AbortController();
    listRuns({ limit: 1, pipelineId }, controller.signal)
      .then((page) => {
        const newest = page.items[0];
        // A run started here meanwhile is newer than anything listed.
        if (newest) {
          setLatest((known) =>
            known?.pipelineId === pipelineId ? known : { pipelineId, runId: newest.id },
          );
        }
      })
      .catch(() => {
        // No history to show is not worth a message; running still works.
      });
    return () => controller.abort();
  }, [pipelineId]);

  const follow = useCallback(
    (run: Run) => {
      if (run.pipeline_id !== null) setLatest({ pipelineId: run.pipeline_id, runId: run.id });
      adopt(run);
    },
    [adopt],
  );

  return { ...live, follow };
}
