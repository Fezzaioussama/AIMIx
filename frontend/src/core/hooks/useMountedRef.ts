import { useEffect, useRef, type RefObject } from 'react';

/**
 * True while the component is mounted, for async work whose request cannot be
 * cancelled (e.g. a save): its answer is then dropped instead of updating state
 * after the screen is gone (AGENTS.md §8).
 */
export function useMountedRef(): RefObject<boolean> {
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return mounted;
}
