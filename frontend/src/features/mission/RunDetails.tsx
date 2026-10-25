import { ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { Run } from '../../core/api/types';
import { LiveRun } from '../runs/LiveRun';
import { RUN_BUTTON } from '../runs/runButtons';
import type { FollowedRun } from '../runs/useFollowedRun';

/** A finished run folds away, so its deliverables are what the pane leads with. */
function startsOpen(run: Run): boolean {
  return run.status !== 'succeeded';
}

/**
 * The live run (`LiveRun`, as it is): its diagram, status bar with Stop and Resume, every
 * step and its tools. Open while the run works or stopped short, folded once it is done.
 * The pane keys it by run, so a new run starts afresh; a status change within one run
 * resets it (React's "state from props" pattern).
 */
export function RunDetails({ run, followed }: { run: Run; followed: FollowedRun }) {
  const [open, setOpen] = useState(startsOpen(run));
  const [seenStatus, setSeenStatus] = useState(run.status);

  if (seenStatus !== run.status) {
    setSeenStatus(run.status);
    setOpen(startsOpen(run));
  }

  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
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
        onResume={() => void followed.resume()}
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
