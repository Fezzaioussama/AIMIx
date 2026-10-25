/**
 * Short phrases that mean "start the mission now" rather than a change to the team.
 * Only whole phrases count, so "run the research in parallel" stays a change request.
 */
const RUN_PHRASES: ReadonlySet<string> = new Set([
  'run',
  'run it',
  'run this',
  'run now',
  'run it now',
  'run the mission',
  'run my mission',
  'run the team',
  'start',
  'start it',
  'start now',
  'start the run',
  'start the mission',
  'go',
  'go ahead',
  'lets go',
  'launch',
  'launch it',
  'do it',
  'execute',
  'execute it',
]);

/** Courtesy words around a phrase: "ok, run it please". */
const COURTESY = /^(?:please|ok|okay|yes|great|perfect|now)\s+|\s+(?:please|now)$/g;

/** Whether a message asks AIMIx to run the mission, e.g. "Run it!" or "go ahead please". */
export function isRunRequest(text: string): boolean {
  const plain = text
    .toLowerCase()
    .replace(/['’]/g, '')
    .replace(/[^a-z]+/g, ' ')
    .trim();
  return RUN_PHRASES.has(plain) || RUN_PHRASES.has(plain.replace(COURTESY, '').trim());
}
