import { ListChecks } from 'lucide-react';

import { RunStatusBadge } from '../runs/RunStatusBadge';
import { isActive } from '../runs/runStatus';
import { Deliverables } from './Deliverables';
import { PaneHeader } from './PaneHeader';
import { filesRefreshKey, RecentFiles } from './RecentFiles';
import { RunDetails } from './RunDetails';
import type { Mission } from './useMission';

/**
 * The right pane: the mission's newest run (the live run, folded away once it is done),
 * its deliverables up front, and the newest files in the workspace.
 */
export function ResultsPane({ mission }: { mission: Mission }) {
  const { followed, team } = mission;
  const { run } = followed;
  return (
    <>
      <PaneHeader pane="results" icon={ListChecks}>
        {run !== null && <RunStatusBadge status={run.status} />}
      </PaneHeader>
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-5 sm:px-5">
        {run !== null && <RunDetails key={run.id} run={run} followed={followed} />}
        <Deliverables run={run} team={team.pipeline} />
        <RecentFiles
          refreshKey={filesRefreshKey(run?.id ?? null, run !== null && isActive(run.status))}
        />
      </div>
    </>
  );
}
