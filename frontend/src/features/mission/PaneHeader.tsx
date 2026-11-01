import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { FOCUS_RING } from '../../core/ui/focus';
import { PANE_LABELS, paneIds, type PaneId } from './missionPanes';

interface PaneHeaderProps {
  pane: PaneId;
  icon: LucideIcon;
  /** A tab names the pane at every width (two columns), not only below `xl`. */
  tabbed?: boolean;
  /** Controls and status on the right. */
  children?: ReactNode;
}

/** Where a tab names the pane, the title is for screen readers and the bar only shows
 * when it has controls. */
const LOOKS = {
  // Below `xl` only: from `xl` the pane sits beside the others, titled.
  titled: {
    bar: 'max-xl:justify-end sm:px-5 xl:min-h-14',
    empty: 'max-xl:sr-only',
    heading: 'max-xl:sr-only',
  },
  tabbed: { bar: 'justify-end sm:px-5', empty: 'sr-only', heading: 'sr-only' },
};

/**
 * A pane's title bar. Its heading takes focus when the pane is brought forward. On a
 * narrow screen the tab already names the pane, so the title is for screen readers
 * there and the bar only shows when it has controls.
 */
export function PaneHeader({ pane, icon: Icon, tabbed = false, children }: PaneHeaderProps) {
  const look = tabbed ? LOOKS.tabbed : LOOKS.titled;
  return (
    <div
      className={`flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-white/[0.06] px-4 py-2 ${look.bar} ${children ? '' : look.empty}`}
    >
      {!tabbed && (
        <Icon aria-hidden="true" className="hidden size-4 shrink-0 text-sky-300 xl:block" />
      )}
      <h2
        id={paneIds(pane).heading}
        tabIndex={-1}
        className={`min-w-0 flex-1 truncate rounded text-xs font-semibold tracking-widest text-slate-300 uppercase focus:outline-none ${FOCUS_RING} ${look.heading}`}
      >
        {PANE_LABELS[pane]}
      </h2>
      {children}
    </div>
  );
}
