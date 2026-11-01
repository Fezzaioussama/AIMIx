import { useCallback, type RefCallback } from 'react';

import { WORKSPACE_PICTURE } from '../markdown/renderMarkdown';
import { loadPicture } from './useImagePreview';

/**
 * A ref for an element holding rendered Markdown: it loads each picture the text names
 * by workspace path (renderMarkdown leaves those without a `src`). It runs again when
 * `html` changes, since new HTML brings new images, and detaching cancels the downloads.
 */
export function useWorkspacePictures(html: string): RefCallback<HTMLElement> {
  return useCallback(
    (element: HTMLElement | null) => {
      if (!element) return;
      const controller = new AbortController();
      for (const image of element.querySelectorAll<HTMLImageElement>(`img[${WORKSPACE_PICTURE}]`)) {
        loadPicture(image.getAttribute(WORKSPACE_PICTURE) ?? '', controller.signal)
          .then((url) => {
            if (!controller.signal.aborted) image.src = url;
          })
          .catch(() => {
            // The picture's alt text stays in its place; the Files page still has it.
          });
      }
      return () => controller.abort();
    },
    // `html` is not read, but each new value is new <img> elements to load.
    [html],
  );
}
