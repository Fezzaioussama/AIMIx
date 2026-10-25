import { useCallback, useRef, useState } from 'react';

import type { PipelineStep } from '../../core/api/types';
import { paneIds } from './missionPanes';

export interface StepDrawerState {
  /** The agent being edited, read from the team as it is now; null when closed. */
  step: PipelineStep | null;
  /** Opens (or switches to) an agent. Remembers where focus was, to give it back. */
  open: (order: number) => void;
  /** Closes it and hands focus back to where it came from. */
  close: () => void;
  /** Closes it without moving focus, e.g. when the team was replaced under it. */
  dismiss: () => void;
}

/**
 * Which agent the drawer edits. It follows the team: an agent that no longer exists
 * closes it. Closing returns focus to the graph node that opened it, or to the team's
 * heading when that node is gone (a removed agent).
 */
export function useStepDrawer(steps: PipelineStep[]): StepDrawerState {
  const [order, setOrder] = useState<number | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const step = steps.find((candidate) => candidate.order === order) ?? null;

  // React's "adjust state when props change": the agent was removed, so nothing is open.
  if (order !== null && step === null) setOrder(null);

  const open = useCallback((next: number) => {
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
    setOrder(next);
  }, []);

  const dismiss = useCallback(() => setOrder(null), []);

  const close = useCallback(() => {
    setOrder(null);
    const back = opener.current?.isConnected
      ? opener.current
      : document.getElementById(paneIds('team').heading);
    back?.focus();
  }, []);

  return { step, open, close, dismiss };
}
