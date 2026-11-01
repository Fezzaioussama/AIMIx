import { useCallback, useEffect, useRef, useState } from 'react';

import { useMountedRef } from './useMountedRef';

const COPIED_FEEDBACK_MS = 1500;

export type CopyStatus = 'idle' | 'copied' | 'failed';

/** The same content twice: formatted for a rich editor, plain for a text field. */
export interface RichText {
  html: string;
  text: string;
}

/**
 * Formatted where the browser allows it, plain text otherwise. The first write starts
 * inside the click, as Safari requires.
 */
async function writeRich({ html, text }: RichText): Promise<void> {
  if (typeof ClipboardItem === 'function') {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }),
        }),
      ]);
      return;
    } catch {
      // Some browsers refuse rich content; plain text below still copies the words.
    }
  }
  await navigator.clipboard.writeText(text);
}

/**
 * Copy to the clipboard and say how it went: 'copied' for a moment, then 'idle', or
 * 'failed' when the browser refuses (an insecure origin, a denied permission). The
 * reset timer is cleared on unmount (§8).
 */
export function useCopyToClipboard() {
  const [status, setStatus] = useState<CopyStatus>('idle');
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const mounted = useMountedRef();

  useEffect(() => () => clearTimeout(timer.current), []);

  const settle = useCallback(
    async (write: () => Promise<void>) => {
      clearTimeout(timer.current);
      let outcome: CopyStatus = 'copied';
      try {
        await write();
      } catch {
        outcome = 'failed';
      }
      if (!mounted.current) return;
      setStatus(outcome);
      if (outcome === 'copied') {
        timer.current = setTimeout(() => setStatus('idle'), COPIED_FEEDBACK_MS);
      }
    },
    [mounted],
  );

  const copy = useCallback(
    (text: string) => settle(() => navigator.clipboard.writeText(text)),
    [settle],
  );
  const copyRich = useCallback((content: RichText) => settle(() => writeRich(content)), [settle]);

  return { status, copy, copyRich };
}
