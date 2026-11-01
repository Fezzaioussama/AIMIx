import type { LucideIcon } from 'lucide-react';
import { useId } from 'react';
import { Link, useLocation } from 'react-router-dom';

import { ActivePill } from './ActivePill';
import { FOCUS_RING } from './focus';

/** A count on an item, read out with what it counts: "Runs, 2 waiting for you". */
export interface NavBadge {
  count: number;
  label: string;
}

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  badge?: NavBadge;
}

export interface NavGroup {
  /** The heading above the group; the first group goes without one. */
  label?: string;
  items: readonly NavItem[];
}

/** An item owns its route and the routes below it, so Runs stays lit on /runs/7. */
function owns(to: string, pathname: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}

const itemClass = (active: boolean) =>
  [
    `relative isolate flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${FOCUS_RING}`,
    active ? 'text-white' : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-50',
  ].join(' ');

function Badge({ count, label }: NavBadge) {
  return (
    <>
      <span
        aria-hidden="true"
        className="ml-auto inline-flex min-w-5 items-center justify-center rounded-full bg-amber-400/20 px-1.5 text-[11px] leading-5 font-semibold text-amber-200 tabular-nums"
      >
        {count}
      </span>
      <span className="sr-only">
        , {count} {label}
      </span>
    </>
  );
}

function NavItemLink({ item, active, pillId }: { item: NavItem; active: boolean; pillId: string }) {
  const Icon = item.icon;
  return (
    <Link to={item.to} aria-current={active ? 'page' : undefined} className={itemClass(active)}>
      {/* The highlight carries a bar in the brand gradient along its left edge. */}
      {active && (
        <ActivePill
          layoutId={pillId}
          className="bg-white/[0.07] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.07)] before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-gradient-to-b before:from-sky-400 before:via-indigo-500 before:to-purple-500"
        />
      )}
      <Icon aria-hidden="true" className={`size-4 shrink-0 ${active ? 'text-sky-300' : ''}`} />
      {item.label}
      {item.badge && item.badge.count > 0 && <Badge {...item.badge} />}
    </Link>
  );
}

interface SidebarNavProps {
  groups: readonly NavGroup[];
  /** One per nav on screen, so the highlight glides within its own nav only. */
  pillId: string;
}

/** The app's sections in labelled groups, the current one highlighted. */
export function SidebarNav({ groups, pillId }: SidebarNavProps) {
  const { pathname } = useLocation();
  const baseId = useId();
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {groups.map((group, index) => {
        const headingId = `${baseId}-${index}`;
        return (
          <div key={group.label ?? index}>
            {group.label && (
              <p
                id={headingId}
                className="mb-1.5 px-3 text-[11px] font-semibold tracking-widest text-slate-400 uppercase"
              >
                {group.label}
              </p>
            )}
            <ul aria-labelledby={group.label ? headingId : undefined} className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.to}>
                  <NavItemLink item={item} active={owns(item.to, pathname)} pillId={pillId} />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
