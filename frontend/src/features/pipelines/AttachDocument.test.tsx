import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { ExtractedDocument } from '../../core/api/types';
import { AttachDocument } from './AttachDocument';
import { RUN_INPUT_MAX_LENGTH } from './pipelineInputs';

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 13,
  pages: 2,
  truncated: false,
};

const page: ExtractedDocument = {
  filename: 'https://example.com/article',
  format: 'html',
  text: 'Page text.',
  characters: 1234,
  pages: null,
  truncated: false,
};

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pdf = () => new File(['%PDF'], 'report.pdf', { type: 'application/pdf' });

function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Attach a document');
}

/** A run input as the form has it: its text box, and the attach row under it. */
function Field({
  initial = '',
  others = 0,
  disabled = false,
}: {
  initial?: string;
  others?: number;
  disabled?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <textarea aria-label="Report" value={value} onChange={(e) => setValue(e.target.value)} />
      <AttachDocument value={value} others={others} disabled={disabled} onChange={setValue} />
    </>
  );
}

const box = () => screen.getByRole('textbox', { name: 'Report' });

describe('AttachDocument: files', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads the chosen file into the input, saying what was added', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Field initial="Summarise this:" />);

    await userEvent.upload(fileInput(), pdf());

    await waitFor(() =>
      expect(box()).toHaveValue('Summarise this:\n\n[Document: report.pdf]\nRevenue grew.'),
    );
    expect(screen.getByRole('status')).toHaveTextContent(
      'report.pdf added · 2 pages · 13 characters',
    );
  });

  it('offers every format the server reads, and names them', () => {
    render(<Field />);

    const accept = fileInput().accept.split(',');
    for (const extension of ['.pdf', '.docx', '.xlsx', '.pptx', '.png', '.jpg', '.tiff', '.csv']) {
      expect(accept).toContain(extension);
    }
    expect(
      screen.getByText('PDF, Word, Excel, PowerPoint, image, HTML, CSV or text file'),
    ).toBeInTheDocument();
  });

  it('shows the backend reason when a file is refused, and adds nothing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: 'unsupported_document', detail: "'.exe' files are not supported." }, 415),
    );
    render(<Field />);

    // `accept` only filters the picker: a person can still choose "All files".
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(fileInput(), new File(['x'], 'tool.exe'));

    expect(await screen.findByRole('alert')).toHaveTextContent("'.exe' files are not supported.");
    expect(box()).toHaveValue('');
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('warns when only part of a long document was kept', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...report, truncated: true }));
    render(<Field />);

    await userEvent.upload(fileInput(), pdf());

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('part of it was left out'),
    );
  });

  it('says what it reads, and blocks a second file meanwhile', async () => {
    let finish: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
    );
    render(<Field />);

    await userEvent.upload(fileInput(), pdf());

    expect(await screen.findByText('Reading…')).toBeInTheDocument();
    expect(screen.getByLabelText('Reading…')).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Reading report.pdf…');

    finish(json(report));
    await waitFor(() => expect(screen.getByLabelText('Attach a document')).toBeEnabled());
  });

  it('is unavailable while the form is busy', () => {
    render(<Field disabled />);
    expect(fileInput()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Add a web page' })).toBeDisabled();
  });

  it('keeps what was typed while a large document was being read', async () => {
    const user = userEvent.setup();
    let finish: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
    );
    render(<Field />);

    await user.upload(fileInput(), pdf());
    await user.type(box(), 'typed meanwhile');
    finish(json(report));

    await waitFor(() =>
      expect(box()).toHaveValue('typed meanwhile\n\n[Document: report.pdf]\nRevenue grew.'),
    );
  });

  it('cancels the upload when it leaves the screen', async () => {
    let signal: AbortSignal | null | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = render(<Field />);

    await userEvent.upload(fileInput(), pdf());
    await screen.findByText('Reading…');
    unmount();

    expect(signal?.aborted).toBe(true);
  });
});

describe('AttachDocument: web pages', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads a page from its link, like a document', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page));
    render(<Field />);

    await user.click(screen.getByRole('button', { name: 'Add a web page' }));
    await user.type(screen.getByRole('textbox', { name: 'Link to a web page' }), 'example.com/a');
    await user.click(screen.getByRole('button', { name: 'Read page' }));

    await waitFor(() =>
      expect(box()).toHaveValue('[Document: https://example.com/article]\nPage text.'),
    );
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.importDocumentUrl);
    expect(JSON.parse(String(init?.body))).toEqual({ url: 'https://example.com/a' });
    expect(screen.getByRole('status')).toHaveTextContent(
      'example.com/article added · 1,234 characters',
    );
  });

  it('shows why a page could not be read', async () => {
    const user = userEvent.setup();
    const blocked =
      'This site didn’t let AIMIx read the page (it may need a sign-in or block automated readers).';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ error: 'page_unreachable', detail: blocked }, 502),
    );
    render(<Field />);

    await user.click(screen.getByRole('button', { name: 'Add a web page' }));
    await user.type(
      screen.getByRole('textbox', { name: 'Link to a web page' }),
      'example.com{Enter}',
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(blocked);
    expect(box()).toHaveValue('');
  });

  it('shares one reading with files: no page while a file is being read', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise<Response>(() => {}));
    render(<Field />);

    await user.upload(fileInput(), pdf());
    await user.click(screen.getByRole('button', { name: 'Add a web page' }));
    await user.type(screen.getByRole('textbox', { name: 'Link to a web page' }), 'example.com');

    expect(screen.getByRole('button', { name: 'Read page' })).toBeDisabled();
  });

  it('offers to read a link the input holds alone, in the link’s place', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page));
    render(<Field initial="https://example.com/a" />);

    expect(screen.getByText('Agents can’t open links on their own.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Read this page into the box' }));

    await waitFor(() =>
      expect(box()).toHaveValue('[Document: https://example.com/article]\nPage text.'),
    );
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      url: 'https://example.com/a',
    });
    expect(screen.queryByText('Agents can’t open links on their own.')).not.toBeInTheDocument();
  });

  it('stops saying a page was added once the input no longer holds it', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(page));
    render(<Field />);
    await user.click(screen.getByRole('button', { name: 'Add a web page' }));
    await user.type(
      screen.getByRole('textbox', { name: 'Link to a web page' }),
      'example.com/a{Enter}',
    );
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent('example.com/article added'),
    );

    await user.clear(box());
    await user.type(box(), 'https://example.com/b');

    expect(screen.getByText('Agents can’t open links on their own.')).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });

  it('says nothing about links among other words', () => {
    render(<Field initial="Summarise https://example.com/a for me" />);
    expect(screen.queryByText('Agents can’t open links on their own.')).not.toBeInTheDocument();
  });
});

describe('AttachDocument: the run’s limit', () => {
  afterEach(() => vi.restoreAllMocks());

  const others = RUN_INPUT_MAX_LENGTH - 30;

  it('warns before adding a document that would pass it, and adds it only if asked', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Field others={others} initial="Look:" />);

    await user.upload(fileInput(), pdf());

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Adding report.pdf would make your inputs 500,013 characters; a run takes at most 500,000.',
    );
    expect(box()).toHaveValue('Look:');

    await user.click(screen.getByRole('button', { name: 'Add it anyway' }));

    expect(box()).toHaveValue('Look:\n\n[Document: report.pdf]\nRevenue grew.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // The question went with its buttons: focus goes back to the picker.
    expect(fileInput()).toHaveFocus();
  });

  it('leaves the document out when asked to', async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Field others={others} />);

    await user.upload(fileInput(), pdf());
    await user.click(await screen.findByRole('button', { name: 'Leave it out' }));

    expect(box()).toHaveValue('');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(fileInput()).toHaveFocus();
  });

  it('adds what still fits without asking', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    render(<Field others={RUN_INPUT_MAX_LENGTH - 100} />);

    await userEvent.upload(fileInput(), pdf());

    await waitFor(() => expect(box()).toHaveValue('[Document: report.pdf]\nRevenue grew.'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
