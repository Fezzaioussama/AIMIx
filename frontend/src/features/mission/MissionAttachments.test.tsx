import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import type { ExtractedDocument, Pipeline } from '../../core/api/types';
import { missionKey } from './missionStorage';
import { renderMission } from './testRender';
import { COMMON_ROUTES, GENERATED, SAVED, deferred, json, routeFetch } from './testData';

const TEXT = 'Revenue grew by twelve percent. '.repeat(10).trim();
const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: TEXT,
  characters: TEXT.length,
  pages: 3,
  truncated: false,
};

const SIZE = `3 pages · ${TEXT.length} characters`;

const composer = () =>
  screen.getByRole('textbox', { name: /Describe your mission|Message AIMIx about your team/ });
const log = () => screen.getByRole('log', { name: 'Conversation with AIMIx' });
const chips = () => screen.getByRole('list', { name: 'Attached documents' });
const pdf = (name = 'report.pdf') => new File(['%PDF'], name, { type: 'application/pdf' });
const BLOCK = `[Document: report.pdf]\n${TEXT}`;
/** The saved team, planned with documents: it has the input meant for them. */
const WITH_DOCUMENTS: Pipeline = {
  ...SAVED,
  inputs: [
    ...SAVED.inputs,
    {
      name: DOCUMENTS_INPUT_NAME,
      label: 'Your documents',
      description:
        'The documents and web pages you added. Their text is put here when the team runs.',
    },
  ],
};

/** A saved team with two inputs, neither meant for documents. */
const TWO_OTHERS: Pipeline = {
  ...SAVED,
  inputs: [...SAVED.inputs, { name: 'focus', label: 'What to focus on', description: '' }],
};

describe('the mission workspace: documents', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('names them on the message that took them, keeps the names for the tab, never the text', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': report,
      'POST /api/pipelines/generate': GENERATED,
    });
    const first = renderMission();

    await user.upload(screen.getByLabelText('Attach a document'), pdf());
    await waitFor(() => expect(chips()).toHaveTextContent(SIZE));
    await user.type(composer(), 'Summarise this for the board{Enter}');

    const sent = await within(log()).findByRole('list', { name: 'Attached' });
    expect(sent).toHaveTextContent('report.pdf');
    expect(sent).toHaveTextContent(SIZE);
    await within(log()).findByText(/Here’s the team I put together/);
    // The documents stay with the mission until it runs.
    expect(chips()).toHaveTextContent('report.pdf');
    expect(screen.getByText('Your team gets these when it runs.')).toBeInTheDocument();
    expect(window.sessionStorage.getItem(missionKey()) ?? '').not.toContain('twelve percent');

    first.unmount();
    cleanup();
    renderMission();

    expect(within(log()).getByRole('list', { name: 'Attached' })).toHaveTextContent('report.pdf');
    // The text was never kept: the box starts empty again.
    expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0);
  });

  it('waits for a document still being read before it sends the mission', async () => {
    const user = userEvent.setup();
    const slow = deferred<Response>();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': () => slow.promise,
      'POST /api/pipelines/generate': GENERATED,
    });
    renderMission();
    await user.type(composer(), 'Summarise this for the board');
    await user.upload(screen.getByLabelText('Attach a document'), pdf());

    await user.keyboard('{Enter}');

    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(screen.getByText('Waiting for report.pdf to be read…')).toBeInTheDocument();
    expect(composer()).toHaveValue('Summarise this for the board');

    slow.resolve(json(report));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled());
  });

  it('Run it opens the form with the documents in it, and empties the box', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': WITH_DOCUMENTS,
      'POST /api/documents/extract': report,
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await user.upload(screen.getByLabelText('Attach a document'), pdf());
    await waitFor(() => expect(chips()).toHaveTextContent('3 pages'));
    await user.click(screen.getByRole('button', { name: 'Run it' }));

    expect(await within(log()).findByLabelText(/Your documents/)).toHaveValue(BLOCK);
    expect(within(log()).getByLabelText(/Your company/)).toHaveValue('');
    await waitFor(() => expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0));
    expect(within(log()).getByRole('list', { name: 'Attached' })).toHaveTextContent('report.pdf');
  });

  it('Run it puts them in the only input of a team that has one', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'POST /api/documents/extract': report,
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.upload(screen.getByLabelText('Attach a document'), pdf());
    await waitFor(() => expect(chips()).toHaveTextContent('3 pages'));

    await user.click(screen.getByRole('button', { name: 'Run it' }));

    expect(await within(log()).findByLabelText(/Your company/)).toHaveValue(BLOCK);
    await waitFor(() => expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0));
    expect(screen.queryByText(/isn’t in the run form/)).not.toBeInTheDocument();
  });

  it('asks which input the documents go in when the team has none meant for them', async () => {
    const user = userEvent.setup();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': TWO_OTHERS,
      'POST /api/documents/extract': report,
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.upload(screen.getByLabelText('Attach a document'), pdf());
    await waitFor(() => expect(chips()).toHaveTextContent('3 pages'));

    await user.click(screen.getByRole('button', { name: 'Run it' }));

    const company = await within(log()).findByLabelText(/Your company/);
    expect(company).toHaveValue('');
    expect(chips()).toHaveTextContent('report.pdf');
    expect(
      screen.getByText(
        'report.pdf isn’t in the run form: your team has no input meant for documents. ' +
          'Put it in:',
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Your company' }));

    expect(company).toHaveValue(BLOCK);
    await waitFor(() => expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0));
    expect(composer()).toHaveFocus();
  });

  it('keeps what one run cannot take for the next, and says so', async () => {
    const user = userEvent.setup();
    const LONG = 'y'.repeat(120_000);
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': WITH_DOCUMENTS,
      'POST /api/documents/extract': (init: RequestInit | undefined) => ({
        ...report,
        filename: ((init?.body as FormData).get('file') as File).name,
        text: LONG,
        characters: LONG.length,
      }),
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    const names = ['a.pdf', 'b.pdf', 'c.pdf', 'd.pdf', 'e.pdf'];
    await user.upload(screen.getByLabelText('Attach a document'), names.map(pdf));
    await waitFor(() => expect(within(chips()).getAllByText(/120,000 characters/)).toHaveLength(5));

    await user.click(screen.getByRole('button', { name: 'Run it' }));
    await user.type(await within(log()).findByLabelText(/Your company/), 'Acme');

    await waitFor(() => expect(within(chips()).getAllByRole('listitem')).toHaveLength(1));
    expect(
      screen.getByText(
        'e.pdf isn’t in the run form: with it, the run’s inputs would pass 500,000 ' +
          'characters. It stays here for your next run.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeEnabled();
  });

  it('the run waits for a document of the box still being read for it', async () => {
    const user = userEvent.setup();
    const slow = deferred<Response>();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': WITH_DOCUMENTS,
      'POST /api/documents/extract': () => slow.promise,
    });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);
    await user.upload(screen.getByLabelText('Attach a document'), pdf());

    await user.click(screen.getByRole('button', { name: 'Run it' }));
    await user.type(await within(log()).findByLabelText(/Your company/), 'Acme');
    await user.type(within(log()).getByLabelText(/Your documents/), 'Also this note.');

    expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeDisabled();
    expect(within(log()).getByText('Waiting for report.pdf to be read…')).toBeInTheDocument();

    slow.resolve(json(report));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Run Pipeline' })).toBeEnabled());
    expect(within(log()).getByLabelText(/Your documents/)).toHaveValue(
      `Also this note.\n\n${BLOCK}`,
    );
  });

  it('asks for the documents again when the team needs them and has none', async () => {
    const user = userEvent.setup();
    routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': WITH_DOCUMENTS });
    renderMission('/mission/7');
    await within(log()).findByText(/Here’s your “Competitor brief” team/);

    await user.click(screen.getByRole('button', { name: 'Run it' }));

    const field = await within(log()).findByLabelText(/Your documents/);
    expect(
      within(log()).getByText(
        'Attach your documents again under “Your documents”: AIMIx keeps only their names, ' +
          'not their text.',
      ),
    ).toBeInTheDocument();
    // Its description promises text that nothing will put there.
    expect(field).not.toHaveAttribute('placeholder', expect.stringContaining('put here'));
  });
});
