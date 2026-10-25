import { NavLink } from 'react-router-dom';

import { ActivePill } from '../../core/ui/ActivePill';
import { useWaitingRuns } from '../runs/useWaitingRuns';

const LINKS = [
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/auto-pipeline', label: 'Auto Pipeline' },
  { to: '/templates', label: 'Templates' },
  { to: '/runs', label: 'Runs' },
] as const;

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'relative isolate rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
    isActive ? 'text-sky-200' : 'text-slate-400 hover:text-slate-50',
  ].join(' ');

/** How many runs wait for the person: a number on the tab, and the same in words. */
function WaitingBadge({ count }: { count: number }) {
  return (
    <>
      <span
        aria-hidden="true"
        className="ml-1.5 inline-flex min-w-4 items-center justify-center rounded-full bg-amber-400/20 px-1 text-[10px] leading-4 font-semibold text-amber-200 tabular-nums"
      >
        {count}
      </span>
      <span className="sr-only">, {count} waiting for you</span>
    </>
  );
}

/**
 * Sub-navigation shared by the pipeline screens, the template gallery and the run
 * history (AGENTS.md §3). The Runs tab counts the runs waiting for the person to
 * approve an action.
 */
export function PipelineNav() {
  const waiting = useWaitingRuns();
  return (
    <nav className="inline-flex gap-1 rounded-lg border border-white/10 bg-slate-950/50 p-1">
      {LINKS.map((link) => (
        <NavLink key={link.to} to={link.to} className={linkClass}>
          {({ isActive }) => (
            <>
              {isActive && (
                <ActivePill
                  layoutId="pipeline-nav"
                  className="bg-sky-400/15 shadow-[inset_0_0_0_1px_rgba(56,189,248,0.3)]"
                />
              )}
              {link.label}
              {link.to === '/runs' && waiting > 0 && <WaitingBadge count={waiting} />}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
