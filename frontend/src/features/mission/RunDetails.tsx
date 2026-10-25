import { ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { Run, RunStatus } from '../../core/api/types';
import { LiveRun } from '../runs/LiveRun';
import { RUN_BUTTON } from '../runs/runButtons';
import type { FollowedRun } from '../runs/useFollowedRun';

/** A finished run folds away, so its deliverables are what the pane leads with. */
function startsOpen(run: Run): boolean {
  return run.status !== 'succeeded';
}

/** What the person last chose for the run in this status. */
interface Choice {
  status: RunStatus;
  open: boolean;
}

/**
 * The live run (`LiveRun`, as it is): its diagram, status bar with Stop and Resume, every
 * step and its tools. Open while the run works or stopped short, folded once it is done.
 * The person can fold or unfold it; that choice holds while the run stays in the same
 * status, and the run's own state decides again when it changes. The pane keys this by
 * run, so a new run starts afresh.
 */
export function RunDetails({ run, followed }: { run: Run; followed: FollowedRun }) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const open = choice !== null && choice.status === run.status ? choice.open : startsOpen(run);

  return (
    <details
      open={open}
      onToggle={(event) => setChoice({ status: run.status, open: event.currentTarget.open })}
      className="group rounded-2xl border border-white/10 bg-slate-900/40 px-4 pb-4"
    >
      <summary className="-mx-2 flex cursor-pointer list-none items-center gap-2 rounded-lg px-2 py-3 text-base font-semibold text-white select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          aria-hidden="true"
          className="size-4 shrink-0 text-slate-400 transition-transform group-open:rotate-90 motion-reduce:transition-none"
        />
        Run details
      </summary>
      <LiveRun
        run={run}
        onStop={() => void followed.stop()}
        onResume={(budget) => void followed.resume(budget)}
        onApprove={(approvalId) => void followed.approve(approvalId)}
        onDecline={(approvalId) => void followed.decline(approvalId)}
        busy={followed.busy}
        error={followed.error}
        actions={
          <Link to={`/runs/${run.id}`} className={RUN_BUTTON.neutral}>
            Open in Runs
          </Link>
        }
      />
    </details>
  );
}
