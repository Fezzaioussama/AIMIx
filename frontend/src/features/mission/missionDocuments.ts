import {
  DOCUMENTS_INPUT_NAME,
  PLAN_DOCUMENT_EXCERPT_CHARS,
  PLAN_DOCUMENT_NAME_MAX_LENGTH,
} from '../../core/api/pipelines';
import type { PlanDocument } from '../../core/api/planningTypes';
import type { ExtractedDocument, PipelineInput } from '../../core/api/types';
import {
  appendDocument,
  RUN_INPUT_MAX_LENGTH,
  runInputSize,
  type RunDraft,
} from '../pipelines/pipelineInputs';
import { linksIn, sameAddress } from '../pipelines/webLinks';
import type { DocumentNote } from './missionMessages';

/**
 * The documents and web pages a person adds to a mission in the message box. They belong
 * to the mission until a run takes them: the planner reads the start of each, the run gets
 * the whole text, and the conversation keeps only their names and sizes.
 */

export interface PendingBase {
  id: string;
  kind: 'file' | 'link';
  /** The file's name, or the link as it was given. */
  source: string;
  /** What makes a file the same one again: its name, size and date (a link's is itself). */
  key: string;
}

/** One document of the box: being read, read, or not readable (with the server's reason). */
export type PendingDocument = PendingBase &
  (
    | { state: 'reading' }
    | { state: 'read'; document: ExtractedDocument }
    | { state: 'failed'; error: string }
  );

/** The documents read so far, in the order they were added. */
export function readDocuments(items: PendingDocument[]): ExtractedDocument[] {
  return items.flatMap((item) => (item.state === 'read' ? [item.document] : []));
}

/** What the person's message keeps of a document: its name and size, never its text. */
export function noteOf(document: ExtractedDocument): DocumentNote {
  return { name: document.filename, pages: document.pages, characters: document.characters };
}

/** The first `max` UTF-16 units of `text`; an emoji is two of them, never sent half. */
function startOf(text: string, max: number): string {
  const cut = text.slice(0, max);
  return /[\uD800-\uDBFF]$/.test(cut) ? cut.slice(0, -1) : cut;
}

/**
 * What the planner reads of a document: its name, its size and the start of its text. A
 * redirect can make a page's address longer than the planner takes, so it is cut too.
 */
export function planDocumentOf(document: ExtractedDocument): PlanDocument {
  const note = noteOf(document);
  return {
    ...note,
    name: startOf(note.name, PLAN_DOCUMENT_NAME_MAX_LENGTH),
    excerpt: startOf(document.text, PLAN_DOCUMENT_EXCERPT_CHARS),
  };
}

/** Where `documentsTarget` puts documents for a team without named inputs: its free text. */
export const FREE_TEXT = '';

/**
 * Where a run form takes the box's documents: the input meant for them (a plan made with
 * documents always has one), the free text of a team without named inputs, or the only
 * input of a team with one (there is nowhere else). Null when several inputs are all
 * meant for something else: the person picks one, AIMIx never guesses.
 */
export function documentsTarget(inputs: PipelineInput[]): string | null {
  if (inputs.length === 0) return FREE_TEXT;
  if (inputs.some((field) => field.name === DOCUMENTS_INPUT_NAME)) return DOCUMENTS_INPUT_NAME;
  return inputs.length === 1 ? inputs[0].name : null;
}

/** The run form with `document` after what `target` (an input, or FREE_TEXT) holds. */
function withDocument(draft: RunDraft, target: string, document: ExtractedDocument): RunDraft {
  if (target === FREE_TEXT) return { ...draft, text: appendDocument(draft.text, document) };
  const value = appendDocument(draft.values[target] ?? '', document);
  return { ...draft, values: { ...draft.values, [target]: value } };
}

/** A run form with documents put in, and which of them it took. */
export interface Placement {
  draft: RunDraft;
  placed: ExtractedDocument[];
}

/**
 * The run form with the documents added to `target`, in order, each after what is there,
 * while the run can still take them: one that would put its inputs past
 * RUN_INPUT_MAX_LENGTH is left out (it is not in `placed`).
 */
export function withDocuments(
  draft: RunDraft,
  inputs: PipelineInput[],
  target: string,
  documents: ExtractedDocument[],
): Placement {
  return documents.reduce<Placement>(
    (so, document) => {
      const next = withDocument(so.draft, target, document);
      if (runInputSize(inputs, next) > RUN_INPUT_MAX_LENGTH) return so;
      return { draft: next, placed: [...so.placed, document] };
    },
    { draft, placed: [] },
  );
}

/** Read documents waiting in the box while a run form is open without them. */
export interface DocumentPlacement {
  /** Their names, as the box shows them. */
  names: string[];
  /** The inputs to pick from, as the team has none meant for documents; empty when they are
   * left out because the run cannot take more (they wait for the next run). */
  choices: PipelineInput[];
  /** Puts them in the input picked, as far as they fit. */
  place: (input: string) => void;
}

/** The key of a file in the box: the same file chosen again has the same one. */
export function fileKey(file: File): string {
  return [file.name, file.size, file.lastModified].join('\u0000');
}

/** The links in the box, as they were given and, once read, where each led. */
function linkAddresses(items: PendingDocument[]): string[] {
  return items.flatMap((item) => {
    if (item.kind !== 'link') return [];
    return item.state === 'read' ? [item.source, item.document.filename] : [item.source];
  });
}

/** Whether the box holds this file (by `fileKey`) or this page (by either address) already. */
export function isAttached(
  wanted: Pick<PendingBase, 'kind' | 'key'>,
  items: PendingDocument[],
): boolean {
  if (wanted.kind === 'file') {
    return items.some((item) => item.kind === 'file' && item.key === wanted.key);
  }
  return linkAddresses(items).some((known) => sameAddress(known, wanted.key));
}

/** The first link in a message that is not attached yet, by what was asked or where it led. */
export function unattachedLink(text: string, items: PendingDocument[]): string | null {
  const fresh = linksIn(text).find((link) => !isAttached({ kind: 'link', key: link }, items));
  return fresh ?? null;
}
