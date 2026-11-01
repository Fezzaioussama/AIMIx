import { describe, expect, it } from 'vitest';

import type { ExtractedDocument, PipelineInput, Run } from '../../../core/api/types';
import { appendDocument } from '../../pipelines/pipelineInputs';
import { makeRun } from '../testData';
import { givenParts, givenSummary } from './runGiven';

/** What the server ends a document's text with (backend/api/services/documents/). */
const TRUNCATION_NOTE = '\n\n[Document truncated: the rest was not included.]';
const notRead = (pages: string) =>
  `\n\n[Not read: ${pages} (looks scanned: under 50 characters of text, and OCR is not available).]`;

const BODY = 'Loop helps small shops keep their regulars. '.repeat(10).trim();

function documentOf(filename: string, text: string): ExtractedDocument {
  return { filename, format: 'pdf', text, characters: text.length, pages: 3, truncated: false };
}

const runGiven = (input: string): Run => makeRun({ input });

describe('givenParts', () => {
  it('reads back what appendDocument wrote: typed text, a document and a web page', () => {
    const pdf = documentOf('brief.pdf', BODY);
    const page = documentOf('https://www.example.com/launch/plan', `${BODY} Page.`);
    const parts = givenParts(runGiven(appendDocument(appendDocument('Launch Loop', pdf), page)));
    expect(
      parts.map(({ label, kind, name, characters, notes }) => [
        label,
        kind,
        name,
        characters,
        notes,
      ]),
    ).toEqual([
      ['Your description', 'text', 'Your description', 11, []],
      ['Your description', 'document', 'brief.pdf', BODY.length, []],
      ['Your description', 'page', 'example.com/launch/plan', BODY.length + 6, []],
    ]);
    expect(parts[1].text).toBe(BODY);
  });

  it('labels the parts of named inputs by their labels', () => {
    const inputs: PipelineInput[] = [
      { name: 'brief', label: 'Product brief', description: '' },
      { name: 'tone', label: '', description: '' },
    ];
    const run = makeRun({
      input: '',
      inputs: { brief: appendDocument('', documentOf('brief.pdf', BODY)), tone: 'Warm' },
      definition: { ...makeRun().definition, inputs },
    });
    expect(givenParts(run).map(({ label, kind, name }) => [label, kind, name])).toEqual([
      ['Product brief', 'document', 'brief.pdf'],
      ['tone', 'text', 'tone'],
    ]);
  });

  it('says when part of a document was left out, and counts without the note', () => {
    const [, part] = givenParts(
      runGiven(appendDocument('Go', documentOf('big.pdf', `${BODY}${TRUNCATION_NOTE}`))),
    );
    expect(part.notes).toEqual([
      { kind: 'truncated', words: 'Part of big.pdf was left out because it was too long.' },
    ]);
    expect(part.characters).toBe(BODY.length);
    expect(part.text).toBe(BODY);
  });

  it('names the pages that could not be read, with an en dash', () => {
    const text = `${BODY}${notRead('pages 4-7')}${notRead('page 9')}${notRead('pages 1-2, 11')}`;
    const [part] = givenParts(runGiven(appendDocument('', documentOf('scan.pdf', text))));
    expect(part.notes.map((note) => note.words)).toEqual([
      'Pages 4–7 of scan.pdf could not be read.',
      'Page 9 of scan.pdf could not be read.',
      'Pages 1–2, 11 of scan.pdf could not be read.',
    ]);
    expect(part.notes.every((note) => note.kind === 'unread')).toBe(true);
    expect(part.characters).toBe(BODY.length);
  });

  it('reads the real note of a scanned first page', () => {
    const text = `Cover${notRead('page 1')}`;
    const [part] = givenParts(runGiven(appendDocument('', documentOf('scan.pdf', text))));
    expect(part.notes).toEqual([
      { kind: 'unread', words: 'Page 1 of scan.pdf could not be read.' },
    ]);
    expect(part.text).toBe('Cover');
  });

  it('says when little text came from a document, only without a note from the server', () => {
    const [thin] = givenParts(runGiven(appendDocument('', documentOf('logo.pdf', 'Loop'))));
    expect(thin.notes).toEqual([
      { kind: 'thin', words: 'Only 4 characters of text came from logo.pdf.' },
    ]);
    const [cut] = givenParts(
      runGiven(appendDocument('', documentOf('logo.pdf', `Loop${TRUNCATION_NOTE}`))),
    );
    expect(cut.notes.map((note) => note.kind)).toEqual(['truncated']);
  });

  it('says a typed link was given as a link, not as the page', () => {
    const parts = givenParts(runGiven('Compare with https://example.com/pricing.'));
    expect(parts.map(({ kind, name }) => [kind, name])).toEqual([
      ['text', 'Your description'],
      ['link', 'example.com/pricing'],
    ]);
    expect(parts[1].notes).toEqual([
      { kind: 'link', words: 'example.com/pricing was given as a link, not as the page’s text.' },
    ]);
  });

  it('gives a link typed alone as a link only', () => {
    const parts = givenParts(runGiven('https://example.com/pricing'));
    expect(parts.map((part) => part.kind)).toEqual(['link']);
  });

  it('leaves out a typed link whose page was read in too', () => {
    const page = documentOf('https://example.com/pricing', BODY);
    const parts = givenParts(runGiven(appendDocument('Compare https://example.com/pricing', page)));
    expect(parts.map((part) => part.kind)).toEqual(['text', 'page']);
  });

  it('has nothing for an empty input', () => {
    expect(givenParts(runGiven(''))).toEqual([]);
  });
});

describe('givenSummary', () => {
  it('names the documents, pages and links, not the typed text', () => {
    const pdf = documentOf('brief.pdf', BODY);
    const parts = givenParts(runGiven(appendDocument('See https://example.com/a', pdf)));
    expect(givenSummary(parts)).toEqual(['example.com/a', 'brief.pdf']);
  });
});
