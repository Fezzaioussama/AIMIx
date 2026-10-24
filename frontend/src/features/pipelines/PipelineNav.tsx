import { NavLink } from 'react-router-dom';

import { ActivePill } from '../../core/ui/ActivePill';

const LINKS = [
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/auto-pipeline', label: 'Auto Pipeline' },
  { to: '/templates', label: 'Templates' },
] as const;

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'relative isolate rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
    isActive ? 'text-sky-200' : 'text-slate-400 hover:text-slate-50',
  ].join(' ');

/** Sub-navigation shared by the pipeline screens (AGENTS.md §3). */
export function PipelineNav() {
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
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
