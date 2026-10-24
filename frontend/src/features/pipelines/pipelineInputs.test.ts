import { describe, expect, it } from 'vitest';

import type { ExtractedDocument, PipelineInput } from '../../core/api/types';
import {
  addInput,
  appendDocument,
  documentSummary,
  inputNameProblem,
  inputsSummary,
  isRunReady,
  runRequest,
  toInputName,
  unknownPlaceholders,
} from './pipelineInputs';

const topic: PipelineInput = { name: 'topic', label: 'Topic', description: '' };
const audience: PipelineInput = { name: 'audience', label: '', description: '' };

describe('toInputName', () => {
  it('turns typing into a snake_case placeholder name', () => {
    expect(toInputName('Target Audience')).toBe('target_audience');
    expect(toInputName('tone-of-voice!')).toBe('tone_of_voice');
    expect(toInputName('x'.repeat(50))).toHaveLength(40);
  });
});

describe('inputNameProblem', () => {
  it('accepts a valid, unique name', () => {
    expect(inputNameProblem('topic', [topic, audience])).toBeNull();
  });

  it.each([
    ['', 'Start with a letter'],
    ['2nd', 'Start with a letter'],
    ['_x', 'Start with a letter'],
    ['input', 'reserved'],
  ])('rejects %j', (name, problem) => {
    expect(inputNameProblem(name, [])).toContain(problem);
  });

  it('flags a name two inputs share', () => {
    expect(inputNameProblem('topic', [topic, { ...audience, name: 'topic' }])).toContain(
      'Another input',
    );
  });
});

describe('addInput', () => {
  it('appends an input with the first free field name', () => {
    const inputs = addInput([{ ...topic, name: 'field_2' }]);
    expect(inputs.map((field) => field.name)).toEqual(['field_2', 'field_3']);
    expect(addInput([]).map((field) => field.name)).toEqual(['field_1']);
  });
});

describe('unknownPlaceholders', () => {
  it('lists placeholders nothing fills, once each, ignoring other braces', () => {
    const prompt = 'Use {input}, {topic}, {tone} and {tone} with {"a": 1}';
    expect(unknownPlaceholders(prompt, [topic])).toEqual(['tone']);
  });
});

describe('inputsSummary', () => {
  it('lists declared inputs by label, else shows the typed text', () => {
    expect(inputsSummary([topic, audience], 'ignored')).toBe('Topic · audience');
    expect(inputsSummary([], 'seed')).toBe('seed');
    expect(inputsSummary([], '')).toBe('Your text');
  });
});

describe('run drafts', () => {
  it('needs the text, or every declared input, to be filled', () => {
    expect(isRunReady([], { text: ' ', values: {} })).toBe(false);
    expect(isRunReady([], { text: 'go', values: {} })).toBe(true);
    expect(isRunReady([topic, audience], { text: '', values: { topic: 'bees' } })).toBe(false);
    expect(
      isRunReady([topic, audience], { text: '', values: { topic: 'bees', audience: 'kids' } }),
    ).toBe(true);
  });

  it('sends the text, or only the values of declared inputs', () => {
    expect(runRequest([], { text: 'go', values: { topic: 'stale' } })).toEqual({ input: 'go' });
    expect(runRequest([topic], { text: 'stale', values: { topic: 'bees', old: 'x' } })).toEqual({
      inputs: { topic: 'bees' },
    });
  });
});

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 13,
  pages: 2,
  truncated: false,
};

describe('appendDocument', () => {
  it('starts an empty input with the document, labelled with its source', () => {
    expect(appendDocument('', report)).toBe('[Document: report.pdf]\nRevenue grew.');
    expect(appendDocument('  \n ', report)).toBe('[Document: report.pdf]\nRevenue grew.');
  });

  it('keeps what was already typed and separates the document from it', () => {
    expect(appendDocument('Summarise this:  \n', report)).toBe(
      'Summarise this:\n\n[Document: report.pdf]\nRevenue grew.',
    );
  });

  it('can add a second document after the first', () => {
    const once = appendDocument('', report);
    const twice = appendDocument(once, { ...report, filename: 'notes.txt', text: 'More.' });
    expect(twice).toBe('[Document: report.pdf]\nRevenue grew.\n\n[Document: notes.txt]\nMore.');
  });
});

describe('documentSummary', () => {
  it('says what was added, with pages and a thousands separator', () => {
    expect(documentSummary({ ...report, characters: 24310 })).toBe(
      'report.pdf added · 2 pages · 24,310 characters',
    );
  });

  it('omits pages for unpaged formats and uses the singular for one page', () => {
    expect(documentSummary({ ...report, pages: null })).toBe('report.pdf added · 13 characters');
    expect(documentSummary({ ...report, pages: 1 })).toContain('1 page ·');
  });

  it('warns when part of the document was left out', () => {
    expect(documentSummary({ ...report, truncated: true })).toMatch(/part of it was left out$/);
  });
});
