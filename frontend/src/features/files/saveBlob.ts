/** How long a finished download keeps its object URL; some browsers read it late. */
const REVOKE_AFTER_MS = 30_000;

/** Hands downloaded content to the browser as a file to save, under `filename`. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}
