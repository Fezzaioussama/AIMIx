import { useEffect, useState } from 'react';

import { downloadFile } from '../api/files';

/** A blob as a data: URL, which the page's Content-Security-Policy lets an <img> show. */
function dataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/**
 * A picture of the user's workspace, fetched with the session header (a token never
 * goes in a URL), ready for an <img>; null while it loads or if it cannot be loaded.
 * Unmounting cancels the download.
 */
export function useImagePreview(path: string): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    downloadFile(path, controller.signal)
      .then(dataUrl)
      .then((url) => {
        if (!controller.signal.aborted) setSrc(url);
      })
      .catch(() => {
        // No preview: the file's row still names it, and the Files page downloads it.
      });
    return () => controller.abort();
  }, [path]);

  return src;
}
