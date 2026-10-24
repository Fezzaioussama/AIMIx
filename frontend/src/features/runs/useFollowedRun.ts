import type { Pipeline, Run } from '../../core/api/types';
import { elapsedMs } from '../../core/time';
import { isActive, ranThisVersion } from './runStatus';
import { useLatestRun, type LatestRunState } from './useLatestRun';

export interface FollowedRun extends LatestRunState {
  /** A run of this pipeline is queued or running. */
  active: boolean;
  /** The run, when it executed exactly the pipeline on screen: the diagram shows it. */
  shown: Run | null;
  shownActive: boolean;
  /** How long the shown run took, once it has ended. */
  shownElapsedMs: number | null;
}

/**
 * The builder's view of its pipeline's newest run (`useLatestRun`). The
 * diagram may show only a run of exactly the version on screen: after an edit,
 * or for a run of an earlier version, the run stays reachable from its status
 * bar but leaves the diagram alone.
 */
export function useFollowedRun(pipeline: Pipeline, dirty: boolean): FollowedRun {
  const latest = useLatestRun(pipeline.id);
  const { run } = latest;
  const shown = run !== null && !dirty && ranThisVersion(run, pipeline) ? run : null;
  const shownActive = shown !== null && isActive(shown.status);
  const ended = shown !== null && !shownActive;
  return {
    ...latest,
    active: run !== null && isActive(run.status),
    shown,
    shownActive,
    shownElapsedMs: ended ? elapsedMs(shown.started_at, shown.finished_at, Date.now()) : null,
  };
}
