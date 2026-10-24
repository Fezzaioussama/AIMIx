import { useEffect, useState } from 'react';

/** How often a live elapsed time is redrawn. */
export const CLOCK_TICK_MS = 1000;

/** The current time, refreshed every second while `ticking` (live elapsed times). */
export function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!ticking) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, [ticking]);

  return now;
}
