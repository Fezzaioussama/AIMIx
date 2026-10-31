/** App routes that more than one feature links to, declared once (AGENTS.md §3). */

/** Where a signed-in person lands: the mission workspace. */
export const HOME_PATH = '/mission';

/** The mission workspace: a new mission, or a saved one (a pipeline) by its id. */
export function missionPath(pipelineId?: number): string {
  return pipelineId === undefined ? HOME_PATH : `${HOME_PATH}/${pipelineId}`;
}

/** The screen a path belongs to: its first segment, so /runs and /runs/7 are one. */
export function sectionOf(pathname: string): string {
  return pathname.split('/')[1] ?? '';
}

/** The legal pages: public, in French (the operator's jurisdiction), text in features/legal. */
export const LEGAL_NOTICE_PATH = '/legal';
export const PRIVACY_PATH = '/privacy';
export const TERMS_PATH = '/terms';

export const LEGAL_LINKS = [
  { path: LEGAL_NOTICE_PATH, label: 'Legal notice' },
  { path: PRIVACY_PATH, label: 'Privacy policy' },
  { path: TERMS_PATH, label: 'Terms of use' },
] as const;

export type LegalPath = (typeof LEGAL_LINKS)[number]['path'];
