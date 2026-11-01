import { useCallback, useState } from 'react';

import { extractDocument, importDocumentFromUrl } from '../../core/api/documents';
import { errorMessage } from '../../core/api/errorMessage';
import type { ExtractedDocument } from '../../core/api/types';
import { useCancellableRequest } from '../../core/hooks/useCancellableRequest';
import { useLatest } from '../../core/hooks/useLatest';
import { documentSummary } from './pipelineInputs';
import { linkLabel } from './webLinks';

/** Where a read document goes, and whether to ask first. `link` is the page's, if any. */
export interface DocumentTarget {
  add: (document: ExtractedDocument, link: string | null) => void;
  /** Why adding it needs the person's say-so (it would pass a limit), or null. */
  warning: (document: ExtractedDocument, link: string | null) => string | null;
}

/** A document read but not added yet, waiting for "Add it anyway" or "Leave it out". */
export interface HeldDocument {
  document: ExtractedDocument;
  link: string | null;
  warning: string;
}

interface ReadState {
  /** What is being read (a file's name or a page's link), or '' when nothing is. */
  reading: string;
  /** Why the last one could not be read. */
  error: string;
  /** What the last one added, and the name its text is headed with in the input. */
  notice: string;
  added: string;
  held: HeldDocument | null;
}

export interface DocumentReader extends ReadState {
  readFile: (file: File) => void;
  readPage: (url: string) => void;
  /** Adds the held document anyway, or leaves it out. */
  keep: () => void;
  dismiss: () => void;
}

const IDLE: ReadState = { reading: '', error: '', notice: '', added: '', held: null };

type Load = (signal: AbortSignal) => Promise<ExtractedDocument>;

function addedState(document: ExtractedDocument): ReadState {
  return { ...IDLE, notice: documentSummary(document), added: document.filename };
}

/**
 * Reads a file or a web page through the backend and hands the result to `target`: one
 * reading, error, notice and cancellation for both (two loaders). The target is read when
 * the document arrives, not when it was asked for, so text typed meanwhile is kept. A
 * newer read replaces one still going, and leaving the screen cancels it.
 */
export function useAttachDocument(target: DocumentTarget): DocumentReader {
  const [state, setState] = useState<ReadState>(IDLE);
  const latest = useLatest(target);
  const { start, finish } = useCancellableRequest();

  const deliver = useCallback(
    (document: ExtractedDocument, link: string | null) => {
      const warning = latest.current.warning(document, link);
      if (warning !== null) return setState({ ...IDLE, held: { document, link, warning } });
      latest.current.add(document, link);
      setState(addedState(document));
    },
    [latest],
  );

  const read = useCallback(
    async (name: string, load: Load, link: string | null) => {
      const controller = start();
      setState({ ...IDLE, reading: name });
      try {
        const document = await load(controller.signal);
        if (finish(controller)) deliver(document, link);
      } catch (cause) {
        if (!finish(controller)) return;
        setState({ ...IDLE, error: errorMessage(cause, 'The document could not be read.') });
      }
    },
    [deliver, finish, start],
  );

  const readFile = useCallback(
    (file: File) => void read(file.name, (signal) => extractDocument(file, signal), null),
    [read],
  );
  const readPage = useCallback(
    (url: string) => void read(linkLabel(url), (signal) => importDocumentFromUrl(url, signal), url),
    [read],
  );

  const keep = () => {
    if (state.held === null) return;
    latest.current.add(state.held.document, state.held.link);
    setState(addedState(state.held.document));
  };

  return { ...state, readFile, readPage, keep, dismiss: () => setState(IDLE) };
}
