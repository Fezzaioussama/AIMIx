import { useCallback, useEffect, useState } from 'react';

import { paneIds, type PaneId } from './missionPanes';

export interface Panes {
  /** The pane a narrow screen shows; a wide screen shows all three. */
  active: PaneId;
  /** The person picked a tab: it switches, and focus stays on the tab. */
  select: (pane: PaneId) => void;
  /** Something sent the person to a pane (a "See the team" link): bring it forward and
   * move focus to its heading, so keyboard and screen-reader users arrive with it. */
  show: (pane: PaneId) => void;
}

/** Which pane is in front, and sending focus to a pane once it is on screen. */
export function usePanes(): Panes {
  const [active, setActive] = useState<PaneId>('chat');
  // A new object per request, so asking twice for the same pane still focuses it.
  const [focusRequest, setFocusRequest] = useState<{ pane: PaneId } | null>(null);

  useEffect(() => {
    if (focusRequest === null) return;
    document.getElementById(paneIds(focusRequest.pane).heading)?.focus();
  }, [focusRequest]);

  const show = useCallback((pane: PaneId) => {
    setActive(pane);
    setFocusRequest({ pane });
  }, []);

  return { active, select: setActive, show };
}
