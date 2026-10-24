import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from '../../core/api/client';
import { extractDocument } from '../../core/api/documents';
import type { ExtractedDocument } from '../../core/api/types';
import { documentSummary } from './pipelineInputs';

interface AttachDocument {
  /** A file is being uploaded and read. */
  reading: boolean;
  /** Why the last file could not be read; empty when it could. */
  error: string;
  /** What the last file added; empty until one does. */
  notice: string;
  attach: (file: File) => Promise<void>;
}

/**
 * Reads a chosen file through the backend and hands the result to `onDocument`.
 * The callback is read at the moment the file finishes, not when it was chosen, so
 * text typed while a large PDF was being read is not overwritten. A newer file
 * replaces one still being read, and leaving the screen cancels the request.
 */
export function useAttachDocument(
  onDocument: (document: ExtractedDocument) => void,
): AttachDocument {
  const [reading, setReading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const latest = useRef(onDocument);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => {
    latest.current = onDocument;
  });
  useEffect(() => () => inFlight.current?.abort(), []);

  const attach = useCallback(async (file: File) => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    setReading(true);
    setError('');
    setNotice('');
    try {
      const document = await extractDocument(file, controller.signal);
      latest.current(document);
      setNotice(documentSummary(document));
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'aborted') return;
      setError(cause instanceof Error ? cause.message : 'The document could not be read.');
    } finally {
      if (inFlight.current === controller) setReading(false);
    }
  }, []);

  return { reading, error, notice, attach };
}
