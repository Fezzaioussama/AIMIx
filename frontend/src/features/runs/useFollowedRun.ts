import type { Pipeline, Run } from '../../core/api/types';
import { isActive, ranThisVersion } from './runStatus';
import { useLatestRun, type LatestRunState } from './useLatestRun';

export interface FollowedRun extends LatestRunState {
  /** A run of this pipeline is queued or running. */
  active: boolean;
  /** The run, when it executed exactly the pipeline on screen: the diagram shows it. */
  shown: Run | null;
  shownActive: boolean;
}

/**
 * The builder's view of its pipeline's newest run (`useLatestRun`). The
 * diagram may show only a run of exactly the version on screen: after an edit,
 * or for a run of an earlier version, the run keeps its report but leaves the
 * diagram alone.
 */
export function useFollowedRun(pipeline: Pipeline, dirty: boolean): FollowedRun {
  const latest = useLatestRun(pipeline.id);
  const { run } = latest;
  const shown = run !== null && !dirty && ranThisVersion(run, pipeline) ? run : null;
  const shownActive = shown !== null && isActive(shown.status);
  return {
    ...latest,
    active: run !== null && isActive(run.status),
    shown,
    shownActive,
  };
}
