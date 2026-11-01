import { useReducedMotion } from 'motion/react';
import { useCallback } from 'react';

/**
 * Brings `targetId` into view, then moves focus to `focusId` (the target itself by default),
 * a heading or toggle with `tabIndex=-1`, without a second scroll. `block` is 'start' for a
 * jump to a part of the report, 'nearest' for a bottom "Hide …" going back to its toggle.
 */
export type Jump = (targetId: string, focusId?: string, block?: ScrollLogicalPosition) => void;

/**
 * The report's in-page jumps (M12): JumpLinks, "Review the request", "Read it above", "Read
 * the check above". Smooth unless the person asked for reduced motion.
 */
export function useJump(): Jump {
  const reduced = useReducedMotion();
  return useCallback(
    (targetId, focusId = targetId, block = 'start') => {
      // jsdom has no scrollIntoView.
      document
        .getElementById(targetId)
        ?.scrollIntoView?.({ behavior: reduced ? 'auto' : 'smooth', block });
      document.getElementById(focusId)?.focus({ preventScroll: true });
    },
    [reduced],
  );
}
