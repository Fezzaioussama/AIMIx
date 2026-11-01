import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ExtractedDocument, PipelineInput, Run } from '../../../core/api/types';
import { appendDocument } from '../../pipelines/pipelineInputs';
import { makeRun } from '../testData';
import { givenParts } from './runGiven';
import { GivenLine, RunGiven } from './RunGiven';

/** What the server ends a document's text with (backend/api/services/documents/). */
const TRUNCATION_NOTE = '\n\n[Document truncated: the rest was not included.]';
const NOT_READ =
  '\n\n[Not read: pages 4-7 (looks scanned: under 50 characters of text, and OCR is not available).]';

const BODY = 'Loop helps small shops keep their regulars. '.repeat(10).trim();

function documentOf(filename: string, text: string): ExtractedDocument {
  return { filename, format: 'pdf', text, characters: text.length, pages: 3, truncated: false };
}

/** A run given `typed`, then each document in turn, as the run form puts them together. */
function given(typed: string, ...documents: ExtractedDocument[]): Run {
  return makeRun({ input: documents.reduce(appendDocument, typed) });
}

function renderAppendix(run: Run) {
  return render(<RunGiven parts={givenParts(run)} level={3} />);
}

describe('GivenLine', () => {
  it('names what the team was given', () => {
    render(
      <GivenLine
        run={given(
          'Launch Loop',
          documentOf('brief.pdf', BODY),
          documentOf('https://www.example.com/launch', BODY),
        )}
      />,
    );

    expect(
      screen.getByText('Given to your team: brief.pdf and example.com/launch.'),
    ).toBeInTheDocument();
  });

  it('names three, then counts the rest', () => {
    const names = ['a.pdf', 'b.pdf', 'c.pdf', 'd.pdf'];

    render(<GivenLine run={given('Go', ...names.map((name) => documentOf(name, BODY)))} />);

    expect(
      screen.getByText('Given to your team: a.pdf, b.pdf, c.pdf and 1 more.'),
    ).toBeInTheDocument();
  });

  it('warns in amber about anything that may be missing', () => {
    render(
      <GivenLine
        run={given(
          'Go',
          documentOf('big.pdf', `${BODY}${TRUNCATION_NOTE}`),
          documentOf('scan.pdf', `${BODY}${NOT_READ}`),
          documentOf('thin.pdf', 'Too short.'),
        )}
      />,
    );

    for (const words of [
      'Part of big.pdf was left out because it was too long.',
      'Pages 4–7 of scan.pdf could not be read.',
      'Only 10 characters of text came from thin.pdf.',
    ]) {
      expect(screen.getByText(words).parentElement).toHaveClass('text-amber-300');
    }
  });

  it('says quietly that a link was given as a link, not as the page', () => {
    render(<GivenLine run={given('Use https://example.com/launch for the tone')} />);

    expect(screen.getByText('Given to your team: example.com/launch.')).toBeInTheDocument();
    expect(
      screen.getByText('example.com/launch was given as a link, not as the page’s text.')
        .parentElement,
    ).toHaveClass('text-slate-400');
  });

  it('says nothing when only text was typed', () => {
    const { container } = render(<GivenLine run={given('Launch Loop')} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe('RunGiven', () => {
  it('lists each part with its kind and size, and the start of its text', () => {
    renderAppendix(
      given(
        'Launch Loop',
        documentOf('brief.pdf', BODY),
        documentOf('https://www.example.com/launch', 'Short page.'),
      ),
    );

    const typed = screen.getByRole('group', { name: 'Your description' });
    expect(typed).toHaveTextContent('Launch Loop');
    expect(typed).toHaveAttribute('tabindex', '0');
    expect(screen.getByText('11 characters')).toBeInTheDocument();
    expect(screen.getByText(`Document · ${BODY.length} characters`)).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'brief.pdf' })).toHaveTextContent(BODY);
    expect(screen.getByText('Web page · 11 characters')).toBeInTheDocument();
    expect(screen.getByText('Only 11 characters of text came from example.com/launch.'));
    // One input: no label above its parts.
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('shows the first 2,000 characters of a long text, and says how much there is', () => {
    const long = 'x'.repeat(2500);

    renderAppendix(given('', documentOf('long.pdf', long)));

    expect(screen.getByRole('group', { name: 'long.pdf' }).textContent).toHaveLength(2000);
    // countOf groups the digits once it formats with formatCount (needs_from_others).
    expect(screen.getByText(/^Showing the first 2,000 of 2,500 characters\.$/)).toBeInTheDocument();
  });

  it('lists a link with no text box, saying it was only a link', () => {
    renderAppendix(given('See https://example.com/launch'));

    expect(screen.getByText('Link')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'example.com/launch' })).toBeNull();
    expect(
      screen.getByText('example.com/launch was given as a link, not as the page’s text.'),
    ).toBeInTheDocument();
  });

  it('puts the parts of several named inputs under their labels', () => {
    const inputs: PipelineInput[] = [
      { name: 'brief', label: 'Product brief', description: '' },
      { name: 'tone', label: '', description: '' },
    ];
    const run = makeRun({
      input: '',
      inputs: { brief: appendDocument('', documentOf('brief.pdf', BODY)), tone: 'Warm' },
      definition: { ...makeRun().definition, inputs },
    });

    renderAppendix(run);

    const [brief, tone] = screen.getAllByRole('heading', { level: 5 });
    expect(brief).toHaveTextContent('Product brief');
    expect(tone).toHaveTextContent('tone');
    expect(within(brief.parentElement as HTMLElement).getByText('brief.pdf')).toBeInTheDocument();
    expect(within(tone.parentElement as HTMLElement).getByText('Warm')).toBeInTheDocument();
  });
});
