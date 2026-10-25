import { useCallback, useState } from 'react';

import { adoptedId } from './missionAddress';

interface Shown {
  /** The mission the address names: undefined for a new one. */
  id: number | undefined;
  /** Changes whenever the workspace must start afresh (it is the React `key`). */
  epoch: number;
}

/**
 * Tells the page when to rebuild the workspace. Opening another mission, or starting a
 * new one, replaces it with a fresh one. A new mission's first save also changes the
 * address (to its own), but the workspace on screen already is that mission, so it
 * stays: rebuilding it would drop a run that is just being started.
 */
export function useWorkspaceIdentity(routeId: number | undefined, locationState: unknown) {
  const [shown, setShown] = useState<Shown>({ id: routeId, epoch: 0 });

  if (shown.id !== routeId) {
    const sameMission =
      shown.id === undefined && routeId !== undefined && adoptedId(locationState) === routeId;
    setShown({ id: routeId, epoch: sameMission ? shown.epoch : shown.epoch + 1 });
  }

  /** A fresh workspace at the same address, e.g. "New mission" on a mission never saved. */
  const restart = useCallback(
    () => setShown((current) => ({ ...current, epoch: current.epoch + 1 })),
    [],
  );

  return { epoch: shown.epoch, restart };
}
