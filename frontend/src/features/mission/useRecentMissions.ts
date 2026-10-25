import { useEffect, useState } from 'react';

import { listPipelines } from '../../core/api/pipelines';
import type { Pipeline } from '../../core/api/types';

/** How many saved missions the empty workspace offers to reopen. */
export const RECENT_MISSIONS = 4;

/**
 * The newest saved missions (every pipeline is one), for "Pick up where you left off".
 * A failed load just leaves the list out: starting a new mission still works.
 */
export function useRecentMissions(): Pipeline[] {
  const [missions, setMissions] = useState<Pipeline[]>([]);

  useEffect(() => {
    let active = true;
    listPipelines()
      .then((pipelines) => {
        if (active) setMissions(pipelines.slice(0, RECENT_MISSIONS));
      })
      .catch(() => {
        // Optional: the workspace works without it.
      });
    return () => {
      active = false;
    };
  }, []);

  return missions;
}
