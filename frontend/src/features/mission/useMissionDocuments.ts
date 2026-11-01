import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';

import { extractDocument, importDocumentFromUrl } from '../../core/api/documents';
import { errorMessage } from '../../core/api/errorMessage';
import { MAX_PLAN_DOCUMENTS } from '../../core/api/pipelines';
import type { ExtractedDocument } from '../../core/api/types';
import { useLatest } from '../../core/hooks/useLatest';
import { documentDetails } from '../pipelines/pipelineInputs';
import { sourceLabel } from '../pipelines/webLinks';
import {
  fileKey,
  isAttached,
  readDocuments,
  type PendingBase,
  type PendingDocument,
} from './missionDocuments';
import { newMessageId } from './missionMessages';

export interface MissionDocuments {
  items: PendingDocument[];
  /** The documents read so far, in the order they were added. */
  read: ExtractedDocument[];
  /** The first one still being read, by name; '' when none is. */
  reading: string;
  /** The box holds as many as a mission takes. */
  full: boolean;
  /** Why some were not added (already there, or no room), or that the box is full; '' otherwise. */
  notice: string;
  /** What just happened to one, for screen readers: reading, ready, removed, in the form. */
  status: string;
  addFiles: (files: File[]) => void;
  addLink: (address: string) => void;
  /** Takes one out of the box, cancelling its reading. */
  remove: (id: string) => void;
  /** Lets go of the documents a run form took, and of the ones that could not be read. */
  release: (taken: ExtractedDocument[]) => void;
}

/** Hands a read document to an open run form; false when none is open. */
export type DocumentSink = (document: ExtractedDocument) => boolean;

interface Ask extends Omit<PendingBase, 'id'> {
  load: (signal: AbortSignal) => Promise<ExtractedDocument>;
}

const NOWHERE: DocumentSink = () => false;
const UNREADABLE = 'It could not be read.';

/** What the last addition left out: the ones already there, and how many found no room. */
interface Refused {
  known: string[];
  leftOut: number;
}

const NONE_REFUSED: Refused = { known: [], leftOut: 0 };

/** "report.pdf is already attached.", for the ones asked for again. */
function knownNotice(names: string[]): string {
  if (names.length === 0) return '';
  return `${names.join(', ')} ${names.length === 1 ? 'is' : 'are'} already attached.`;
}

function limitNotice(leftOut: number, count: number): string {
  if (leftOut > 0) {
    const verb = leftOut === 1 ? 'was' : 'were';
    return `A mission takes up to ${MAX_PLAN_DOCUMENTS} documents, so ${leftOut} ${verb} left out. Remove one to add another.`;
  }
  return count >= MAX_PLAN_DOCUMENTS
    ? `That’s ${MAX_PLAN_DOCUMENTS} documents, the most a mission takes.`
    : '';
}

/** One cancellable request per document; leaving the screen cancels them all. */
function useRequests() {
  const live = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const requests = live.current;
    return () => {
      for (const controller of requests.values()) controller.abort();
      requests.clear();
    };
  }, []);
  return useMemo(
    () => ({
      open(id: string): AbortSignal {
        const controller = new AbortController();
        live.current.set(id, controller);
        return controller.signal;
      },
      /** True, and lets it go, while the request is still wanted. */
      close: (id: string): boolean => live.current.delete(id),
      cancel(id: string) {
        live.current.get(id)?.abort();
        live.current.delete(id);
      },
    }),
    [],
  );
}

/** The documents a mission counts: one that could not be read is only there to say why. */
function counted(items: PendingDocument[]): number {
  return items.filter((item) => item.state !== 'failed').length;
}

function refusedNotice({ known, leftOut }: Refused, count: number): string {
  return [knownNotice(known), limitNotice(leftOut, count)].filter(Boolean).join(' ');
}

function readingStatus(started: PendingDocument[]): string {
  const [first] = started;
  return started.length === 1
    ? `Reading ${sourceLabel(first.source)}…`
    : `Reading ${started.length} documents…`;
}

const fileAsk = (file: File): Ask => ({
  kind: 'file',
  source: file.name,
  key: fileKey(file),
  load: (signal) => extractDocument(file, signal),
});

const linkAsk = (address: string): Ask => ({
  kind: 'link',
  source: address,
  key: address,
  load: (signal) => importDocumentFromUrl(address, signal),
});

/**
 * Reading the documents: `start` reads one and settles it in the list when its answer
 * comes (read, failed, or handed to an open run form through `deliver`); `cancel` stops
 * one and takes it out.
 */
function useReading(
  setItems: Dispatch<SetStateAction<PendingDocument[]>>,
  setStatus: (status: string) => void,
  deliver: DocumentSink,
) {
  const requests = useRequests();
  const sink = useLatest(deliver);

  const settle = useCallback(
    (id: string, next: PendingDocument | null) =>
      setItems((list) => list.flatMap((item) => (item.id !== id ? [item] : next ? [next] : []))),
    [setItems],
  );

  const arrive = useCallback(
    (item: PendingDocument, document: ExtractedDocument) => {
      const name = sourceLabel(document.filename);
      const taken = sink.current(document);
      settle(item.id, taken ? null : { ...item, state: 'read', document });
      setStatus(
        taken ? `${name} is in the run form.` : `${name} is ready: ${documentDetails(document)}.`,
      );
    },
    [setStatus, settle, sink],
  );

  const start = useCallback(
    ({ load, ...ask }: Ask): PendingDocument => {
      const item: PendingDocument = { ...ask, id: newMessageId(), state: 'reading' };
      load(requests.open(item.id)).then(
        (document) => requests.close(item.id) && arrive(item, document),
        (cause: unknown) =>
          requests.close(item.id) &&
          settle(item.id, { ...item, state: 'failed', error: errorMessage(cause, UNREADABLE) }),
      );
      return item;
    },
    [arrive, requests, settle],
  );

  const cancel = useCallback(
    (id: string) => {
      requests.cancel(id);
      settle(id, null);
    },
    [requests, settle],
  );

  return { start, cancel };
}

/**
 * The documents and web pages added to a mission in the message box, each read by the
 * server on its own (several at once; one never waits for another). A document read
 * while a run form is open goes into it through `deliver`; the others wait in the box.
 */
export function useMissionDocuments(deliver: DocumentSink = NOWHERE): MissionDocuments {
  const [items, setItems] = useState<PendingDocument[]>([]);
  const [refused, setRefused] = useState(NONE_REFUSED);
  const [status, setStatus] = useState('');
  const reading = useReading(setItems, setStatus, deliver);

  function add(asks: Ask[]) {
    const fresh = asks.filter((ask) => !isAttached(ask, items));
    const taken = fresh.slice(0, Math.max(0, MAX_PLAN_DOCUMENTS - counted(items)));
    const known = asks.filter((ask) => !fresh.includes(ask)).map((ask) => sourceLabel(ask.source));
    setRefused({ known, leftOut: fresh.length - taken.length });
    if (taken.length === 0) return;
    const started = taken.map(reading.start);
    setItems((list) => [...list, ...started]);
    setStatus(readingStatus(started));
  }

  function remove(id: string) {
    const item = items.find((candidate) => candidate.id === id);
    reading.cancel(id);
    setRefused(NONE_REFUSED);
    if (item) setStatus(`${sourceLabel(item.source)} removed.`);
  }

  function release(taken: ExtractedDocument[]) {
    if (taken.length > 0) setStatus('Your documents are in the run form.');
    // Only what was taken: a document read since then stays for the form or the next run.
    const kept = (item: PendingDocument) =>
      item.state === 'reading' || (item.state === 'read' && !taken.includes(item.document));
    setItems((list) => list.filter(kept));
    setRefused(NONE_REFUSED);
  }

  const pending = items.find((item) => item.state === 'reading');
  return {
    items,
    read: readDocuments(items),
    reading: pending ? sourceLabel(pending.source) : '',
    full: counted(items) >= MAX_PLAN_DOCUMENTS,
    notice: refusedNotice(refused, counted(items)),
    status,
    addFiles: (files) => add(files.map(fileAsk)),
    addLink: (address) => add([linkAsk(address)]),
    remove,
    release,
  };
}
