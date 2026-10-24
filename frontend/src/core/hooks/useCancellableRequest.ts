import { useCallback, useEffect, useRef } from 'react';

/**
 * At most one request in flight, cancelled when the screen goes away (AGENTS.md §8).
 * `start()` aborts the previous request and returns a fresh controller to pass on as the
 * signal; `cancel()` aborts the current one. `finish(controller)` returns true, and lets
 * it go, only while that request is still the current one: a superseded request, or one
 * cut short by leaving the screen, must not update state.
 */
export function useCancellableRequest() {
  const inFlight = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      inFlight.current?.abort();
      inFlight.current = null;
    },
    [],
  );

  const start = useCallback(() => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    return controller;
  }, []);

  const cancel = useCallback(() => {
    inFlight.current?.abort();
  }, []);

  const finish = useCallback((controller: AbortController) => {
    if (inFlight.current !== controller) return false;
    inFlight.current = null;
    return true;
  }, []);

  return { start, cancel, finish };
}
