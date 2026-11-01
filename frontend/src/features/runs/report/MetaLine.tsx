import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { Run } from '../../../core/api/types';
import { useNow } from '../../../core/hooks/useNow';
import { runPath } from '../../../core/routes';
import { elapsedMs, formatDuration } from '../../../core/time';
import { RunCost } from '../RunCost';
import { RunStatusBadge } from '../RunStatusBadge';
import { isActive } from '../runStatus';
import { DOTTED } from './dotted';
import { TEXT_LINK } from './textStyles';

/** One fact of the line; one left empty (RunCost with nothing to say yet) is not shown. */
function Fact({ children }: { children: ReactNode }) {
  return <span className={`${DOTTED.item} empty:hidden`}>{children}</span>;
}

interface MetaLineProps {
  run: Run;
  /** Add "Open in Runs", where the run is shown away from the Runs page. */
  linkToRuns?: boolean;
}

/** "Done · 4 min 54 s · $0.0708 of $1.00 limit · Open in Runs", below the heading. */
export function MetaLine({ run, linkToRuns = false }: MetaLineProps) {
  const active = isActive(run.status);
  const now = useNow(active);
  const elapsed = elapsedMs(run.started_at, run.finished_at, now);
  return (
    <div className={`mt-2 ${DOTTED.frame}`}>
      <p className={`${DOTTED.row} text-sm text-slate-400`}>
        <Fact>
          <RunStatusBadge status={run.status} />
        </Fact>
        {elapsed !== null && (
          <Fact>
            <span className="tabular-nums">{formatDuration(elapsed)}</span>
          </Fact>
        )}
        <Fact>
          <RunCost run={run} active={active} />
        </Fact>
        {linkToRuns && (
          <Fact>
            <Link to={runPath(run.id)} className={TEXT_LINK}>
              Open in Runs
            </Link>
          </Fact>
        )}
      </p>
    </div>
  );
}
