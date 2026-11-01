import { useEffect, useRef, useState } from 'react';

import { useMediaQuery } from '../../core/hooks/useMediaQuery';
import { layoutOf, WIDE_LAYOUT, type Layout } from './missionPanes';
import type { Mission } from './useMission';
import type { Panes } from './usePanes';

export interface MissionLayout {
  layout: Layout;
  /** The team has loaded and its newest run is known; it stays true for the visit. */
  settled: boolean;
}

/**
 * Whether a run that just arrived brings Results forward, by layout (Strategy +
 * Registry, AGENTS.md §7). Settling waits: the run is weighed once the layout is known.
 */
const OPENS_RESULTS: Record<
  Exclude<Layout, 'settling'>,
  (listed: boolean, chosen: boolean) => boolean
> = {
  // A narrow screen opens on the results of a run found with the mission, unless the
  // person already picked a pane; a run started here keeps them in the conversation.
  tabs: (listed, chosen) => listed && !chosen,
  // Three panes already show the results.
  three: () => false,
  // Two columns: each new run's results come forward beside the conversation.
  twoUp: () => true,
};

/**
 * Latched while rendering (adjusting state on a change), so the frame that knows what to
 * show is already the settled one, with no in-between paint.
 */
function useSettled(mission: Mission): boolean {
  const ready = mission.team.status !== 'loading' && mission.followed.checked;
  const [settled, setSettled] = useState(ready);
  if (ready && !settled) setSettled(true);
  return settled || ready;
}

/** Brings a new run's results forward where the layout says so; focus never moves. */
function useOpenOnResults(runId: number | null, layout: Layout, listed: boolean, panes: Panes) {
  const seen = useRef<number | null>(null);
  const { chosen, preset } = panes;
  useEffect(() => {
    if (runId === null || layout === 'settling' || seen.current === runId) return;
    seen.current = runId;
    if (OPENS_RESULTS[layout](listed, chosen)) preset('results');
  }, [runId, layout, listed, chosen, preset]);
}

/**
 * The workspace's layout. A wide screen settles once on three panes (no run yet) or two
 * columns (a run), so nothing snaps from one to the other on load; a narrow one has tabs.
 */
export function useMissionLayout(mission: Mission, panes: Panes): MissionLayout {
  const wide = useMediaQuery(WIDE_LAYOUT);
  const settled = useSettled(mission);
  const { run, listed } = mission.followed;
  const layout = layoutOf(wide, settled, run !== null);
  useOpenOnResults(run?.id ?? null, layout, listed, panes);
  return { layout, settled };
}
