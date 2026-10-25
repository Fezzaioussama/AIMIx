import { ListChecks } from 'lucide-react';

import type { Run } from '../../core/api/types';
import { RunStatusBadge } from '../runs/RunStatusBadge';
import { RUN_BUTTON } from '../runs/runButtons';
import { limitReached } from '../runs/runBudget';
import { isActive, isResumable } from '../runs/runStatus';
import type { FollowedRun } from '../runs/useFollowedRun';
import { Deliverables } from './Deliverables';
import { PaneHeader } from './PaneHeader';
import { filesRefreshKey, RecentFiles } from './RecentFiles';
import { RunDetails } from './RunDetails';
import type { Mission } from './useMission';

/**
 * The run's status and its one control, always in reach at the top of the pane: the
 * full status bar sits inside the run details, which may be folded or further down.
 */
function RunStatusControls({ run, followed }: { run: Run; followed: FollowedRun }) {
  return (
    <>
      <RunStatusBadge status={run.status} />
      {isActive(run.status) && (
        <button
          type="button"
          aria-label="Stop the run"
          disabled={followed.busy}
          onClick={() => void followed.stop()}
          className={RUN_BUTTON.stop}
        >
          Stop
        </button>
      )}
      {/* A run that stopped at its spending limit cannot resume under it: the run details
          (open for a run that stopped short) ask for a higher limit first. */}
      {isResumable(run.status) && limitReached(run) === null && (
        <button
          type="button"
          aria-label="Resume the run"
          disabled={followed.busy}
          onClick={() => void followed.resume()}
          className={RUN_BUTTON.resume}
        >
          Resume
        </button>
      )}
    </>
  );
}

/**
 * The right pane: the mission's deliverables up front, the live run behind them (open
 * while it works, folded once it is done) and the newest files in the workspace.
 */
export function ResultsPane({ mission }: { mission: Mission }) {
  const { followed, team } = mission;
  const { run } = followed;
  return (
    <>
      <PaneHeader pane="results" icon={ListChecks}>
        {run !== null && <RunStatusControls run={run} followed={followed} />}
      </PaneHeader>
      <div className="relative min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-5 sm:px-5">
        <Deliverables run={run} team={team.pipeline} />
        {run !== null && <RunDetails key={run.id} run={run} followed={followed} />}
        <RecentFiles
          refreshKey={filesRefreshKey(run?.id ?? null, run !== null && isActive(run.status))}
        />
      </div>
    </>
  );
}
