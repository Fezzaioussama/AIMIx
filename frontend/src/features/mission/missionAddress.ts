/**
 * The mission's address: `/mission` for a new mission, `/mission/<pipeline id>` for a
 * saved one. A new mission's first save moves it to its own address with router state
 * saying so, and the page keeps the open workspace instead of starting a fresh one.
 */

/** Router state of the address change a mission's first save makes. */
export interface AdoptedState {
  adopted: number;
}

export function adoptedState(pipelineId: number): AdoptedState {
  return { adopted: pipelineId };
}

/** The id a first save just gave the open mission, when the router state says so. */
export function adoptedId(state: unknown): number | undefined {
  return typeof state === 'object' &&
    state !== null &&
    'adopted' in state &&
    typeof state.adopted === 'number'
    ? state.adopted
    : undefined;
}

/** The mission id in the address: undefined for a new mission, null when it is not an id. */
export function parseMissionId(param: string | undefined): number | undefined | null {
  if (param === undefined) return undefined;
  return /^[1-9]\d*$/.test(param) ? Number(param) : null;
}
