import { Link } from 'react-router-dom';

import { LiveRunHeader } from './LiveRunHeader';
import { RUN_BUTTON } from './runButtons';
import type { FollowedRun } from './useFollowedRun';

/** The builder's status bar for its pipeline's newest run: Stop, Resume, Open in Runs. */
export function FollowedRunBar({ followed }: { followed: FollowedRun }) {
  const { run } = followed;
  if (run === null) return null;
  return (
    <LiveRunHeader
      run={run}
      onStop={() => void followed.stop()}
      onResume={(budget) => void followed.resume(budget)}
      busy={followed.busy}
      error={followed.error}
      actions={
        <Link to={`/runs/${run.id}`} className={RUN_BUTTON.neutral}>
          Open in Runs
        </Link>
      }
      note={
        followed.shown ? undefined : (
          <p className="mt-2 text-xs text-slate-400">
            This run used another version of the pipeline; open it in Runs to see its steps.
          </p>
        )
      }
    />
  );
}
