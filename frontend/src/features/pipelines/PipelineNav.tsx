import { NavLink } from 'react-router-dom';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'rounded-md border border-transparent px-3 py-2 text-xs transition-colors',
    isActive
      ? 'border-sky-400/30 bg-sky-400/10 text-sky-400'
      : 'text-slate-400 hover:bg-white/8 hover:text-slate-50',
  ].join(' ');

/** Sub-navigation shared by both pipeline screens (AGENTS.md §3). */
export function PipelineNav() {
  return (
    <nav className="flex gap-1.5">
      <NavLink to="/pipeline" className={linkClass}>
        Pipeline
      </NavLink>
      <NavLink to="/auto-pipeline" className={linkClass}>
        Auto Pipeline
      </NavLink>
    </nav>
  );
}
