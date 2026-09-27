import { useCallback, useEffect, useRef, useState } from 'react';

const COPIED_FEEDBACK_MS = 1500;

/** Copy text and report it briefly; the reset timer is cleared on unmount (§8). */
export function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access can be refused (insecure origin, permissions); the
      // button then simply does not confirm.
      return;
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), COPIED_FEEDBACK_MS);
  }, []);

  return { copied, copy };
}
