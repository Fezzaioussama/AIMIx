/** The workspace's three panes: side by side on a wide screen, tabs on a narrow one. */
export type PaneId = 'chat' | 'team' | 'results';

export const PANE_ORDER: readonly PaneId[] = ['chat', 'team', 'results'];

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
