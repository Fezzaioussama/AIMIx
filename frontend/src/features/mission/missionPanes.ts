/** The workspace's three panes: side by side on a wide screen, tabs on a narrow one. */
export type PaneId = 'chat' | 'team' | 'results';

export const PANE_ORDER: readonly PaneId[] = ['chat', 'team', 'results'];

/** The panes that share the main column beside the conversation once there is a run. */
export const MAIN_PANES: readonly PaneId[] = ['team', 'results'];

export const PANE_LABELS: Record<PaneId, string> = {
  chat: 'Conversation',
  team: 'Team',
  results: 'Results',
};

/** Panes sit side by side from this width (Tailwind's `xl`); below it they are tabs. */
export const WIDE_LAYOUT = '(min-width: 1280px)';

/** A pane's DOM ids: its heading (focused when the pane is brought forward), tab and panel. */
export function paneIds(pane: PaneId) {
  return {
    heading: `mission-${pane}-heading`,
    tab: `mission-${pane}-tab`,
    panel: `mission-${pane}-panel`,
  };
}

/**
 * How the workspace sets out its panes:
 * - `tabs`: a narrow screen, one pane at a time;
 * - `settling`: a wide screen until the team and its newest run are known, so the panes
 *   appear once, in their place, instead of three panes snapping into two columns;
 * - `three`: the conversation, the team and the planned results side by side (no run yet);
 * - `twoUp`: the conversation beside one main column, the team or the run's results.
 */
export type Layout = 'tabs' | 'settling' | 'three' | 'twoUp';

export function layoutOf(wide: boolean, settled: boolean, hasRun: boolean): Layout {
  if (!wide) return 'tabs';
  if (!settled) return 'settling';
  return hasRun ? 'twoUp' : 'three';
}

/** In two columns the main one shows the team when it was picked, else the results. */
export function mainPane(active: PaneId): PaneId {
  return active === 'team' ? 'team' : 'results';
}

/**
 * Each layout's grid. The conversation column keeps the width it has beside three panes
 * at each breakpoint, so it does not jump when a run starts.
 */
export const GRID: Record<Layout, string> = {
  tabs: 'flex',
  settling:
    'grid grid-cols-[20rem_minmax(0,1fr)] grid-rows-[minmax(0,1fr)] 2xl:grid-cols-[24rem_minmax(0,1fr)]',
  three:
    'grid grid-cols-[20rem_minmax(0,1fr)_22rem] grid-rows-[minmax(0,1fr)] 2xl:grid-cols-[24rem_minmax(0,1fr)_26rem]',
  twoUp:
    'grid grid-cols-[20rem_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] 2xl:grid-cols-[24rem_minmax(0,1fr)]',
};

/** Which panes a layout shows, given the one in front (Strategy + Registry, AGENTS.md §7). */
const SHOWN: Record<Layout, (pane: PaneId, active: PaneId) => boolean> = {
  tabs: (pane, active) => pane === active,
  settling: (pane) => pane === 'chat',
  three: () => true,
  twoUp: (pane, active) => pane === 'chat' || pane === mainPane(active),
};

/** A side pane is set off by a hairline and a darker ground. */
const SIDE = 'border-white/[0.06] bg-slate-950/50';

/** Each pane's look and grid cell, by layout. */
const PANE_CLASS: Record<Layout, Partial<Record<PaneId, string>>> = {
  tabs: {},
  settling: { chat: `border-r ${SIDE}` },
  three: { chat: `border-r ${SIDE}`, results: `border-l ${SIDE}` },
  twoUp: {
    chat: `row-span-2 border-r ${SIDE}`,
    team: 'col-start-2 row-start-2',
    results: 'col-start-2 row-start-2',
  },
};

export interface PanePlace {
  shown: boolean;
  /** A tab names the pane (a tab panel), rather than its own heading (a region). */
  tabbed: boolean;
  className: string;
}

/** Where a pane sits in a layout, and whether it is on screen. */
export function panePlace(pane: PaneId, layout: Layout, active: PaneId): PanePlace {
  return {
    shown: SHOWN[layout](pane, active),
    tabbed: layout === 'tabs' || (layout === 'twoUp' && pane !== 'chat'),
    className: PANE_CLASS[layout][pane] ?? '',
  };
}
