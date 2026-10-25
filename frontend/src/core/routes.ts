/** App routes that more than one feature links to, declared once (AGENTS.md §3). */

/** Where a signed-in person lands: the mission workspace. */
export const HOME_PATH = '/mission';

/** The mission workspace: a new mission, or a saved one (a pipeline) by its id. */
export function missionPath(pipelineId?: number): string {
  return pipelineId === undefined ? HOME_PATH : `${HOME_PATH}/${pipelineId}`;
}
