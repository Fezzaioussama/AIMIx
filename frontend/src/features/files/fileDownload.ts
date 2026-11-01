import { downloadFile } from '../../core/api/files';
import { saveBlob } from '../../core/saveBlob';
import { fileName } from './fileFormat';

/**
 * Fetches a workspace file with the session and hands it to the browser under its
 * own name; nothing is saved once `signal` is aborted (the screen is gone).
 */
export async function downloadAndSave(path: string, signal: AbortSignal): Promise<void> {
  const content = await downloadFile(path, signal);
  if (!signal.aborted) saveBlob(content, fileName(path));
}
