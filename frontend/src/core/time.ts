/** Durations and timestamps as screens show them. */

/** Milliseconds from `startedAt` until `finishedAt`, or until `now` while unfinished. */
export function elapsedMs(startedAt: string | null, finishedAt: string | null, now: number) {
  if (!startedAt) return null;
  const end = finishedAt ? Date.parse(finishedAt) : now;
  return Math.max(0, end - Date.parse(startedAt));
}

/** "4.2 s", "3 min 05 s", "1 h 02 min". */
export function formatDuration(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${String(Math.floor(seconds % 60)).padStart(2, '0')} s`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
}

const DATE_TIME = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

/** "Oct 24, 9:58 PM", in the viewer's time zone. */
export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}
