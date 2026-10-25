import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { PANE_LABELS, paneIds, type PaneId } from './missionPanes';

interface PaneHeaderProps {
  pane: PaneId;
  icon: LucideIcon;
  /** Controls and status on the right. */
  children?: ReactNode;
}

/**
 * A pane's title bar. Its heading takes focus when the pane is brought forward. On a
 * narrow screen the tab already names the pane, so the title is for screen readers
 * there and the bar only shows when it has controls.
 */
export function PaneHeader({ pane, icon: Icon, children }: PaneHeaderProps) {
  return (
    <div
      className={`flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-white/[0.06] px-4 py-2 max-xl:justify-end sm:px-5 xl:min-h-14 ${children ? '' : 'max-xl:sr-only'}`}
    >
      <Icon aria-hidden="true" className="hidden size-4 shrink-0 text-sky-300 xl:block" />
      <h2
        id={paneIds(pane).heading}
        tabIndex={-1}
        className="min-w-0 flex-1 truncate rounded text-xs font-semibold tracking-widest text-slate-300 uppercase focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 max-xl:sr-only"
      >
        {PANE_LABELS[pane]}
      </h2>
      {children}
    </div>
  );
}
