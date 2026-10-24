import { useReducedMotion } from 'motion/react';
import { useCallback, useEffect, useState } from 'react';

export const STEP_INTERVAL_MS = 6000;

interface StepCarousel {
  active: number;
  /** Picks a step by hand; automatic advance then stays off for good. */
  select: (index: number) => void;
  /** Whether the steps are currently advancing on their own. */
  auto: boolean;
  /** Pause while the pointer or keyboard focus is inside the carousel. */
  hold: (holding: boolean) => void;
}

/**
 * Cycles through `count` steps on a timer. It stops when the visitor picks a step,
 * pauses while they hover or focus it, and never runs under prefers-reduced-motion,
 * so the content is never changing out from under someone reading it (WCAG 2.2.2).
 */
export function useStepCarousel(count: number): StepCarousel {
  const reduceMotion = useReducedMotion();
  const [active, setActive] = useState(0);
  const [chosen, setChosen] = useState(false);
  const [holding, setHolding] = useState(false);
  const auto = !chosen && !holding && !reduceMotion;

  useEffect(() => {
    if (!auto) return undefined;
    const timer = setTimeout(() => setActive((index) => (index + 1) % count), STEP_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [auto, active, count]);

  const select = useCallback((index: number) => {
    setActive(index);
    setChosen(true);
  }, []);

  return { active, select, auto, hold: setHolding };
}
