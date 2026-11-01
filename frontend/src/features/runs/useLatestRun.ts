import { useCallback, useEffect, useState } from 'react';

import { listRuns } from '../../core/api/runs';
import type { Run } from '../../core/api/types';
import { useRun, type LiveRunState } from './useRun';

interface Latest {
  pipelineId: number;
  runId: number;
  /** Found in the pipeline's history, not started here. */
  listed: boolean;
}

export interface LatestRunState extends LiveRunState {
  /** Follow a run just started here instead. */
  follow: (run: Run) => void;
  /**
   * The history has answered and the run it named (or one started here) has loaded or
   * failed to: what to show is known, so a screen can settle on its layout.
   */
  checked: boolean;
  /** The run followed came from the pipeline's history, not from a start on this screen. */
  listed: boolean;
}

/**
 * The newest run of a pipeline, followed live (`useRun`): loaded when the
 * pipeline opens, so a run started earlier — even before leaving the page —
 * shows again, and replaced by each run started here.
 */
export function useLatestRun(pipelineId: number | undefined): LatestRunState {
  const [latest, setLatest] = useState<Latest | null>(null);
  // The pipeline whose history has answered (or failed to).
  const [lookedUp, setLookedUp] = useState<number | null>(null);
  const followed = latest !== null && latest.pipelineId === pipelineId ? latest : null;
  const live = useRun(followed?.runId ?? null);
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
            known?.pipelineId === pipelineId
              ? known
              : { pipelineId, runId: newest.id, listed: true },
          );
        }
      })
      .catch(() => {
        // No history to show is not worth a message; running still works.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLookedUp(pipelineId);
      });
    return () => controller.abort();
  }, [pipelineId]);

  const follow = useCallback(
    (run: Run) => {
      if (run.pipeline_id !== null) {
        setLatest({ pipelineId: run.pipeline_id, runId: run.id, listed: false });
      }
      adopt(run);
    },
    [adopt],
  );

  const checked =
    followed !== null
      ? live.run !== null || live.error !== ''
      : pipelineId === undefined || lookedUp === pipelineId;
  return { ...live, follow, checked, listed: followed?.listed ?? false };
}
