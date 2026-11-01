/**
 * What a run was given, part by part (pure): what the person typed, each document and web
 * page read into the input (`appendDocument` in pipelines/pipelineInputs.ts writes their
 * "[Document: …]" blocks, and `splitDocuments` there reads them back), and bare links,
 * with notes on whatever may be missing.
 */
import type { Run } from '../../../core/api/types';
import { countOf } from '../../../core/usageFormat';
import { inputLabel, splitDocuments, type HeldDocument } from '../../pipelines/pipelineInputs';
import {
  bareLink,
  isWebAddress,
  linksIn,
  sameAddress,
  sourceLabel,
} from '../../pipelines/webLinks';

/** What one part of a run's input is: typed text, a document, a web page, or a bare link. */
export type GivenKind = 'text' | 'document' | 'page' | 'link';

/** Why a part may hold less than the person meant to give. */
export type NoteKind = 'truncated' | 'unread' | 'thin' | 'link';

export interface Note {
  kind: NoteKind;
  words: string;
}

export interface GivenPart {
  /** The input it came from: "Your description", or a named input's label. */
  label: string;
  kind: GivenKind;
  /** A document's file name, a page's or link's address as people read it, or the label. */
  name: string;
  /** Of `text`. */
  characters: number;
  /** What the team was given, without the server's notes. */
  text: string;
  notes: Note[];
}

/** What a run without named inputs was given: the text the person typed. */
const DESCRIPTION = 'Your description';
/** Fewer characters than this from a document, with no note from the server, is worth a word. */
const THIN_TEXT_CHARS = 200;

/**
 * The notes the server ends a document's text with when it left something out, each on a
 * line of its own: TRUNCATION_NOTE in backend/api/services/documents/extraction.py, and
 * the pages OCR did not read (`PageOcr.omissions` in scans.py).
 */
const SERVER_NOTE_LINE = /^\[(?:Document truncated|Not read): .*\]$/gm;
const TRUNCATED = /^\[Document truncated: /m;
/** "[Not read: page 4 (…).]", "[Not read: pages 1-3, 7 (…).]". */
const NOT_READ = /^\[Not read: (pages?) ([\d, -]+?) \(/gm;

function serverNotes(text: string, name: string): Note[] {
  const notes: Note[] = [];
  if (TRUNCATED.test(text)) {
    notes.push({
      kind: 'truncated',
      words: `Part of ${name} was left out because it was too long.`,
    });
  }
  for (const [, word, pages] of text.matchAll(NOT_READ)) {
    const which = `${word === 'page' ? 'Page' : 'Pages'} ${pages.replace(/-/g, '–')}`;
    notes.push({ kind: 'unread', words: `${which} of ${name} could not be read.` });
  }
  return notes;
}

function documentPart(label: string, held: HeldDocument): GivenPart {
  const name = sourceLabel(held.source);
  const text = held.text.replace(SERVER_NOTE_LINE, '').trimEnd();
  const notes = serverNotes(held.text, name);
  if (notes.length === 0 && text.length < THIN_TEXT_CHARS) {
    const words = `Only ${countOf(text.length, 'character')} of text came from ${name}.`;
    notes.push({ kind: 'thin', words });
  }
  const kind = isWebAddress(held.source) ? 'page' : 'document';
  return { label, kind, name, characters: text.length, text, notes };
}

/** The links typed in, each once, but not one whose page the team was given as well. */
function linkParts(label: string, typed: string, pages: string[]): GivenPart[] {
  const links = [...new Set(linksIn(typed))].filter(
    (link) => !pages.some((page) => sameAddress(page, link)),
  );
  return links.map((link) => {
    const name = sourceLabel(link);
    const words = `${name} was given as a link, not as the page’s text.`;
    return {
      label,
      kind: 'link',
      name,
      characters: link.length,
      text: link,
      notes: [{ kind: 'link', words }],
    };
  });
}

function inputParts(label: string, value: string): GivenPart[] {
  const { typed, documents } = splitDocuments(value);
  const pages = documents.map((held) => held.source).filter(isWebAddress);
  // A link typed alone is its link part, not text as well.
  const text: GivenPart[] =
    typed.trim() !== '' && bareLink(typed) === null
      ? [{ label, kind: 'text', name: label, characters: typed.length, text: typed, notes: [] }]
      : [];
  return [
    ...text,
    ...linkParts(label, typed, pages),
    ...documents.map((held) => documentPart(label, held)),
  ];
}

/** Every part of what the run was given, input by input, in the order it was given. */
export function givenParts(run: Run): GivenPart[] {
  const { inputs } = run.definition;
  if (inputs.length === 0) return inputParts(DESCRIPTION, run.input);
  return inputs.flatMap((field) => inputParts(inputLabel(field), run.inputs[field.name] ?? ''));
}

/** The names of the documents, pages and links given, for "Given to your team: …". */
export function givenSummary(parts: GivenPart[]): string[] {
  return parts.filter((part) => part.kind !== 'text').map((part) => part.name);
}
