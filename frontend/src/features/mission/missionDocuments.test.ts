import { describe, expect, it } from 'vitest';

import {
  DOCUMENTS_INPUT_NAME,
  PLAN_DOCUMENT_EXCERPT_CHARS,
  PLAN_DOCUMENT_NAME_MAX_LENGTH,
} from '../../core/api/pipelines';
import type { ExtractedDocument, PipelineInput } from '../../core/api/types';
import { EMPTY_RUN_DRAFT, RUN_INPUT_MAX_LENGTH } from '../pipelines/pipelineInputs';
import {
  documentsTarget,
  FREE_TEXT,
  noteOf,
  planDocumentOf,
  readDocuments,
  unattachedLink,
  withDocuments,
  type PendingDocument,
} from './missionDocuments';

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 13,
  pages: 2,
  truncated: false,
};

const page: ExtractedDocument = {
  filename: 'https://example.com/a',
  format: 'html',
  text: 'Page text.',
  characters: 10,
  pages: null,
  truncated: false,
};

const company: PipelineInput = { name: 'company', label: 'Your company', description: '' };
const focus: PipelineInput = { name: 'focus', label: 'What to focus on', description: '' };
const documentsInput: PipelineInput = {
  name: DOCUMENTS_INPUT_NAME,
  label: 'Your documents',
  description: '',
};
const BLOCKS =
  '[Document: report.pdf]\nRevenue grew.\n\n[Document: https://example.com/a]\nPage text.';

describe('what goes where', () => {
  it('puts only a document’s name and size on the person’s message', () => {
    expect(noteOf(report)).toEqual({ name: 'report.pdf', pages: 2, characters: 13 });
  });

  it('gives the planner the start of each text', () => {
    const long = { ...report, text: 'a'.repeat(5000), characters: 5000 };
    expect(planDocumentOf(long)).toEqual({
      name: 'report.pdf',
      pages: 2,
      characters: 5000,
      excerpt: 'a'.repeat(PLAN_DOCUMENT_EXCERPT_CHARS),
    });
  });

  it('never cuts a character in two at the end of the excerpt', () => {
    const text = `${'a'.repeat(PLAN_DOCUMENT_EXCERPT_CHARS - 1)}😀 and more`;
    expect(planDocumentOf({ ...report, text }).excerpt).toBe(
      'a'.repeat(PLAN_DOCUMENT_EXCERPT_CHARS - 1),
    );
  });

  it('cuts a page address longer than the planner takes, as a redirect can make it', () => {
    const address = `https://example.com/?${'q'.repeat(PLAN_DOCUMENT_NAME_MAX_LENGTH)}`;
    const planned = planDocumentOf({ ...page, filename: address });
    expect(planned.name).toBe(address.slice(0, PLAN_DOCUMENT_NAME_MAX_LENGTH));
    expect(noteOf({ ...page, filename: address }).name).toBe(address);
  });
});

describe('where a run form takes documents', () => {
  it('in the input meant for them, or the free text of a team without named inputs', () => {
    expect(documentsTarget([company, documentsInput])).toBe(DOCUMENTS_INPUT_NAME);
    expect(documentsTarget([])).toBe(FREE_TEXT);
  });

  it('in the only input of a team that has one: there is nowhere else to put them', () => {
    expect(documentsTarget([company])).toBe('company');
  });

  it('nowhere when several inputs are all meant for something else: AIMIx never guesses', () => {
    expect(documentsTarget([company, focus])).toBeNull();
  });
});

describe('withDocuments', () => {
  it('adds them to the input given, after what it holds', () => {
    const draft = { text: '', values: { company: 'Acme' } };
    expect(withDocuments(draft, [company], 'company', [report, page])).toEqual({
      draft: { text: '', values: { company: `Acme\n\n${BLOCKS}` } },
      placed: [report, page],
    });
  });

  it('or to the free text', () => {
    expect(withDocuments({ text: 'Go', values: {} }, [], FREE_TEXT, [report, page])).toEqual({
      draft: { text: `Go\n\n${BLOCKS}`, values: {} },
      placed: [report, page],
    });
  });

  it('leaves out one the run cannot take on top of the others, and goes on', () => {
    const big = { ...report, filename: 'big.pdf', text: 'x'.repeat(RUN_INPUT_MAX_LENGTH) };
    const inputs = [company, documentsInput];
    const placement = withDocuments(EMPTY_RUN_DRAFT, inputs, DOCUMENTS_INPUT_NAME, [
      report,
      big,
      page,
    ]);
    expect(placement).toEqual({
      draft: { text: '', values: { documents: BLOCKS } },
      placed: [report, page],
    });
  });

  it('changes nothing without documents', () => {
    const draft = { text: 'Go', values: {} };
    expect(withDocuments(draft, [company], 'company', [])).toEqual({ draft, placed: [] });
  });
});

describe('the documents of a mission', () => {
  const items: PendingDocument[] = [
    { id: '1', kind: 'file', source: 'report.pdf', key: 'r', state: 'read', document: report },
    {
      id: '2',
      kind: 'link',
      source: 'https://example.com/old',
      key: 'https://example.com/old',
      state: 'read',
      document: page,
    },
    {
      id: '3',
      kind: 'link',
      source: 'https://example.com/slow',
      key: 'https://example.com/slow',
      state: 'reading',
    },
    { id: '4', kind: 'file', source: 'scan.pdf', key: 's', state: 'failed', error: 'Unreadable.' },
  ];

  it('lists the ones read, in the order they were added', () => {
    expect(readDocuments(items)).toEqual([report, page]);
  });

  it('suggests the first link in a message that is not attached yet', () => {
    expect(unattachedLink('See https://example.com/slow and https://example.org/b.', items)).toBe(
      'https://example.org/b',
    );
    // A link counts as attached by what was asked for and by where it led.
    expect(unattachedLink('https://example.com/old https://example.com/a', items)).toBeNull();
    expect(unattachedLink('No link here', items)).toBeNull();
  });
});
