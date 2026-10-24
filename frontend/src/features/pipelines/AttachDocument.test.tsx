import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ExtractedDocument } from '../../core/api/types';
import { AttachDocument } from './AttachDocument';

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 13,
  pages: 2,
  truncated: false,
};

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pdf = () => new File(['%PDF'], 'report.pdf', { type: 'application/pdf' });

function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Attach a document');
}

describe('AttachDocument', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads the chosen file and hands its text on, saying what was added', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(report));
    const onDocument = vi.fn();
    render(<AttachDocument onDocument={onDocument} />);

    await userEvent.upload(fileInput(), pdf());

    expect(onDocument).toHaveBeenCalledWith(report);
    expect(await screen.findByRole('status')).toHaveTextContent(
      'report.pdf added · 2 pages · 13 characters',
    );
  });

  it('offers every format the server reads, and names them', () => {
    render(<AttachDocument onDocument={vi.fn()} />);

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
    const onDocument = vi.fn();
    render(<AttachDocument onDocument={onDocument} />);

    // `accept` only filters the picker: a person can still choose "All files".
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(fileInput(), new File(['x'], 'tool.exe'));

    expect(await screen.findByRole('alert')).toHaveTextContent("'.exe' files are not supported.");
    expect(onDocument).not.toHaveBeenCalled();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('warns when only part of a long document was kept', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ ...report, truncated: true }));
    render(<AttachDocument onDocument={vi.fn()} />);

    await userEvent.upload(fileInput(), pdf());

    expect(await screen.findByRole('status')).toHaveTextContent('part of it was left out');
  });

  it('blocks a second file while one is being read', async () => {
    let finish: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
    );
    render(<AttachDocument onDocument={vi.fn()} />);

    await userEvent.upload(fileInput(), pdf());

    expect(await screen.findByText('Reading…')).toBeInTheDocument();
    expect(screen.getByLabelText('Reading…')).toBeDisabled();

    finish(json(report));
    await waitFor(() => expect(screen.getByLabelText('Attach a document')).toBeEnabled());
  });

  it('is unavailable while the form is busy', () => {
    render(<AttachDocument onDocument={vi.fn()} disabled />);
    expect(fileInput()).toBeDisabled();
  });

  it('uses the latest callback when the file finishes, not the one from when it was chosen', async () => {
    let finish: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        finish = resolve;
      }),
    );
    const early = vi.fn();
    const late = vi.fn();
    const { rerender } = render(<AttachDocument onDocument={early} />);

    await userEvent.upload(fileInput(), pdf());
    rerender(<AttachDocument onDocument={late} />);
    finish(json(report));

    await waitFor(() => expect(late).toHaveBeenCalledWith(report));
    expect(early).not.toHaveBeenCalled();
  });

  it('cancels the upload when it leaves the screen', async () => {
    let signal: AbortSignal | null | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = render(<AttachDocument onDocument={vi.fn()} />);

    await userEvent.upload(fileInput(), pdf());
    await screen.findByText('Reading…');
    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
