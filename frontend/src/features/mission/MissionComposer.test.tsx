import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { PLAN_DESCRIPTION_MAX_LENGTH } from '../../core/api/pipelines';
import type { ExtractedDocument } from '../../core/api/types';
import { formatCount } from '../../core/usageFormat';
import { REVISION_INSTRUCTION_MAX_LENGTH } from '../pipelines/revision';
import { MissionComposer } from './MissionComposer';
import { deferred, hangUntilAborted, json } from './testData';
import { useMissionDocuments, type DocumentSink } from './useMissionDocuments';

// The microphone itself is covered in core/voice/MicButton.test.tsx: here it just speaks.
vi.mock('../../core/voice/MicButton', () => import('../../core/voice/speakingMic'));

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 195,
  pages: 1,
  truncated: false,
};

const page: ExtractedDocument = {
  filename: 'https://www.example.com/news/today',
  format: 'html',
  text: 'Page text.',
  characters: 2400,
  pages: null,
  truncated: false,
};

const pdf = (name = 'report.pdf') => new File(['%PDF'], name, { type: 'application/pdf' });

interface HarnessProps {
  initial?: string;
  hasTeam?: boolean;
  onChange?: (value: string) => void;
  /** Where a document goes once read: an open run form takes it when this says so. */
  deliver?: DocumentSink;
}

/** The message box as the conversation pane holds it, with the mission's documents. */
function Composer({ initial = '', hasTeam = false, onChange, deliver }: HarnessProps) {
  const [value, setValue] = useState(initial);
  const documents = useMissionDocuments(deliver);
  const field = useRef<HTMLTextAreaElement>(null);
  return (
    <MissionComposer
      ref={field}
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange?.(next);
      }}
      onSend={vi.fn()}
      hasTeam={hasTeam}
      disabled={false}
      documents={documents}
    />
  );
}

const box = () =>
  screen.getByRole('textbox', { name: /Describe your mission|Message AIMIx about your team/ });
const chips = () => screen.getByRole('list', { name: 'Attached documents' });

describe('MissionComposer dictation', () => {
  it('adds the dictated words after the typed mission', async () => {
    const onChange = vi.fn();
    render(<Composer initial="Research our competitors" onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'Dictate your mission' }));

    expect(onChange).toHaveBeenCalledWith('Research our competitors then a reviewer checks it');
  });

  it('dictates a change request once there is a team', async () => {
    const onChange = vi.fn();
    render(<Composer hasTeam onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'Dictate a change to your team' }));

    expect(onChange).toHaveBeenCalledWith('then a reviewer checks it');
  });
});

describe('MissionComposer length', () => {
  it('takes a whole mission before there is a team, and a short change after', () => {
    const { unmount } = render(<Composer />);
    expect(box()).toHaveAttribute('maxLength', String(PLAN_DESCRIPTION_MAX_LENGTH));
    unmount();

    render(<Composer hasTeam />);
    expect(box()).toHaveAttribute('maxLength', String(REVISION_INSTRUCTION_MAX_LENGTH));
  });

  it('says so when the box is full, and what to do with long text', () => {
    render(<Composer initial={'x'.repeat(PLAN_DESCRIPTION_MAX_LENGTH)} />);

    expect(
      screen.getByText(
        'That’s the most a mission description takes (20,000 characters). ' +
          'Attach long text as a document instead.',
      ),
    ).toBeInTheDocument();
  });

  it('says so for a change request too, whose box is shorter', () => {
    render(<Composer hasTeam initial={'x'.repeat(REVISION_INSTRUCTION_MAX_LENGTH)} />);

    expect(
      screen.getByText(
        `That’s the most a change request takes (${formatCount(REVISION_INSTRUCTION_MAX_LENGTH)} ` +
          'characters).',
      ),
    ).toBeInTheDocument();
  });
});

describe('MissionComposer documents', () => {
  afterEach(() => vi.restoreAllMocks());

  it('attaches documents: each chip says it is reading, then what it holds', async () => {
    let answer: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        answer = resolve;
      }),
    );
    render(<Composer />);

    await userEvent.upload(screen.getByLabelText('Attach a document'), pdf());

    const chip = within(chips()).getByRole('listitem');
    expect(chip).toHaveTextContent('report.pdf');
    expect(chip).toHaveTextContent('Reading…');
    // Typing goes on while it is read.
    await userEvent.type(box(), 'Summarise it');
    expect(box()).toHaveValue('Summarise it');

    answer(json(report));

    await waitFor(() => expect(chip).toHaveTextContent('1 page · 195 characters'));
    expect(chip).not.toHaveTextContent('Reading…');
    expect(screen.getByText('report.pdf is ready: 1 page · 195 characters.')).toBeInTheDocument();
  });

  it('shows the server’s message on a document it could not read', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: 'document_unreadable', detail: 'This PDF is protected by a password.' }, 422),
    );
    render(<Composer />);

    await userEvent.upload(screen.getByLabelText('Attach a document'), pdf('locked.pdf'));

    expect(await within(chips()).findByRole('alert')).toHaveTextContent(
      'This PDF is protected by a password.',
    );
  });

  it('removing a document cancels its reading, and focus moves on sensibly', async () => {
    const user = userEvent.setup();
    const signals: (AbortSignal | null | undefined)[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) => {
      signals.push(init?.signal);
      return hangUntilAborted(init);
    });
    render(<Composer />);
    await user.upload(screen.getByLabelText('Attach a document'), [pdf('a.pdf'), pdf('b.pdf')]);

    await user.click(screen.getByRole('button', { name: 'Remove a.pdf' }));

    expect(signals[0]?.aborted).toBe(true);
    expect(signals[1]?.aborted).toBe(false);
    expect(screen.getByRole('button', { name: 'Remove b.pdf' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: 'Remove b.pdf' }));

    expect(box()).toHaveFocus();
    await waitFor(() => expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0));
  });

  it('moves focus on when a focused chip leaves the box for the run form', async () => {
    const user = userEvent.setup();
    const first = deferred<Response>();
    const second = deferred<Response>();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) =>
      ((init?.body as FormData).get('file') as File).name === 'a.pdf'
        ? first.promise
        : second.promise,
    );
    render(<Composer deliver={() => true} />);
    await user.upload(screen.getByLabelText('Attach a document'), [pdf('a.pdf'), pdf('b.pdf')]);

    screen.getByRole('button', { name: 'Remove a.pdf' }).focus();
    first.resolve(json({ ...report, filename: 'a.pdf' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove b.pdf' })).toHaveFocus());

    second.resolve(json({ ...report, filename: 'b.pdf' }));

    await waitFor(() => expect(box()).toHaveFocus());
    await waitFor(() => expect(within(chips()).queryAllByRole('listitem')).toHaveLength(0));
  });

  it('attaches files dropped on the box, which shows it is ready for them', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Composer />);
    const zone = box().closest('[data-dropping]') as HTMLElement;
    expect(zone).toHaveAttribute('data-dropping', 'false');

    fireEvent.dragOver(box(), { dataTransfer: { types: ['Files'], files: [] } });
    expect(zone).toHaveAttribute('data-dropping', 'true');

    fireEvent.drop(box(), { dataTransfer: { types: ['Files'], files: [pdf()] } });

    expect(zone).toHaveAttribute('data-dropping', 'false');
    await waitFor(() => expect(chips()).toHaveTextContent('1 page · 195 characters'));
  });

  it('reads a web page from a link, and gives focus back when done', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page));
    render(<Composer />);
    const toggle = screen.getByRole('button', { name: 'Add a link' });

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.type(
      screen.getByRole('textbox', { name: 'Link to a web page' }),
      'example.com/news/today{Enter}',
    );

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
    // Enter read the page; it did not send the message.
    expect(fetchMock.mock.calls[0][0]).toBe(API.importDocumentUrl);
    await waitFor(() => expect(chips()).toHaveTextContent('example.com/news/today'));
    expect(chips()).toHaveTextContent('2,400 characters');
  });

  it('closes the link field on Escape', async () => {
    const user = userEvent.setup();
    render(<Composer />);
    const toggle = screen.getByRole('button', { name: 'Add a link' });
    await user.click(toggle);

    await user.keyboard('{Escape}');

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });

  it('offers to read a link written in the message', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page));
    render(<Composer initial="Summarise https://www.example.com/news/today for my team" />);

    await user.click(screen.getByRole('button', { name: 'Read example.com for your team' }));

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      url: 'https://www.example.com/news/today',
    });
    expect(box()).toHaveFocus();
    // Once attached, it is not offered again.
    expect(screen.queryByRole('button', { name: /for your team$/ })).not.toBeInTheDocument();
  });

  it('takes at most five documents, and says so', async () => {
    // A fresh answer for each upload: a response's body can be read only once.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(report));
    render(<Composer initial="Compare these with https://www.example.com/news/today" />);

    await userEvent.upload(
      screen.getByLabelText('Attach a document'),
      ['a', 'b', 'c', 'd', 'e', 'f'].map((name) => pdf(`${name}.pdf`)),
    );

    expect(within(chips()).getAllByRole('listitem')).toHaveLength(5);
    await waitFor(() =>
      expect(within(chips()).getAllByText('1 page · 195 characters')).toHaveLength(5),
    );
    expect(within(chips()).queryByRole('alert')).not.toBeInTheDocument();
    expect(
      screen.getByText(/A mission takes up to 5 documents, so 1 was left out/),
    ).toBeInTheDocument();
    // A full box offers no link to read either.
    expect(screen.queryByRole('button', { name: /for your team$/ })).not.toBeInTheDocument();
  });

  it('says the team gets them when it runs, once there is a team', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Composer hasTeam />);

    await userEvent.upload(screen.getByLabelText('Attach a document'), pdf());

    expect(screen.getByText('Your team gets these when it runs.')).toBeInTheDocument();
  });
});
