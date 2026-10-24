import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { FileListing, WorkspaceFile } from '../../core/api/types';
import { FilesPage } from './FilesPage';

const report: WorkspaceFile = {
  path: 'reports/q3.pdf',
  size: 48_213,
  modified_at: '2026-10-24T09:30:00Z',
  type: 'pdf',
};
const notes: WorkspaceFile = {
  path: 'notes.txt',
  size: 5,
  modified_at: '2026-10-24T10:00:00Z',
  type: 'txt',
};

function listingOf(files: WorkspaceFile[]): FileListing {
  return {
    files,
    used_bytes: files.reduce((total, file) => total + file.size, 0),
    quota_bytes: 100_000_000,
    max_file_bytes: 10_000_000,
    allowed_extensions: ['.csv', '.docx', '.pdf', '.txt'],
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>;

/** Answers each "METHOD path" with its handler; anything else fails the test. */
function serve(routes: Record<string, Handler>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`;
    const handler = routes[key];
    return handler ? Promise.resolve(handler(init)) : Promise.reject(new Error(`No ${key}`));
  });
}

function uploaded(init: RequestInit | undefined): File {
  return (init?.body as FormData).get('files') as File;
}

function fileInput(): HTMLInputElement {
  return screen.getByLabelText('Files to upload');
}

describe('FilesPage', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:download');
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => vi.restoreAllMocks());

  it('says what the page is for when there are no files yet', async () => {
    serve({ 'GET /api/files': () => json(listingOf([])) });
    render(<FilesPage />);

    expect(await screen.findByRole('heading', { name: 'No files yet' })).toBeInTheDocument();
    expect(screen.getByText(/Files your agents save appear here/)).toBeInTheDocument();
    expect(screen.getByText(/can also read the files you upload/)).toBeInTheDocument();
    expect(screen.getByText('0 bytes of 100 MB used')).toBeInTheDocument();
    expect(screen.getByText('PDF, Word, text and CSV, up to 10 MB each')).toBeInTheDocument();
  });

  it('lists each file with its folder, size and date', async () => {
    serve({ 'GET /api/files': () => json(listingOf([notes, report])) });
    render(<FilesPage />);

    const list = await screen.findByRole('list', { name: 'Your files' });
    const rows = within(list).getAllByRole('listitem');
    expect(rows.map((row) => row.querySelector('p')?.textContent)).toEqual(['notes.txt', 'q3.pdf']);
    expect(within(rows[1]).getByText(/^reports · 48 KB ·/)).toBeInTheDocument();
    expect(rows[1].querySelector('time')).toHaveAttribute('datetime', report.modified_at);
    expect(screen.getByText('48 KB of 100 MB used')).toBeInTheDocument();
  });

  it('uploads chosen files one by one and adds them to the list', async () => {
    const fetchMock = serve({
      'GET /api/files': () => json(listingOf([])),
      'POST /api/files': (init) => {
        const file = uploaded(init);
        return json([{ ...notes, path: file.name, size: file.size }], 201);
      },
    });
    render(<FilesPage />);
    await screen.findByText('No files yet');

    await userEvent.upload(fileInput(), [
      new File(['hello'], 'a.txt'),
      new File(['world!'], 'b.txt'),
    ]);

    expect(await screen.findByRole('status')).toHaveTextContent('2 files uploaded.');
    const names = within(screen.getByRole('list', { name: 'Your files' }))
      .getAllByRole('listitem')
      .map((row) => row.querySelector('p')?.textContent);
    expect(names).toEqual(['b.txt', 'a.txt']);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  });

  it('offers to replace a file whose name is taken', async () => {
    const replaced: boolean[] = [];
    serve({
      'GET /api/files': () => json(listingOf([notes])),
      'POST /api/files': (init) => {
        const replace = (init?.body as FormData).get('replace') === 'true';
        replaced.push(replace);
        return replace
          ? json([{ ...notes, size: 9 }], 201)
          : json({ error: 'file_exists', detail: "'notes.txt' already exists." }, 409);
      },
    });
    render(<FilesPage />);
    await screen.findByRole('list', { name: 'Your files' });

    await userEvent.upload(fileInput(), new File(['new notes'], 'notes.txt'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'notes.txt: A file with this name already exists.',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Replace' }));

    expect(await screen.findByRole('status')).toHaveTextContent('notes.txt uploaded.');
    expect(screen.queryByRole('alert')).toBeNull();
    expect(replaced).toEqual([false, true]);
    expect(screen.getByText(/^9 bytes ·/)).toBeInTheDocument();
  });

  it('shows why a file was refused next to the upload control', async () => {
    serve({
      'GET /api/files': () => json(listingOf([])),
      'POST /api/files': () =>
        json({ error: 'unsupported_file_type', detail: "'.exe' files cannot be uploaded." }, 415),
    });
    render(<FilesPage />);
    await screen.findByText('No files yet');
    // As if "All files" were picked in the browser's dialog, past its type filter.
    const user = userEvent.setup({ applyAccept: false });

    await user.upload(fileInput(), new File(['MZ'], 'tool.exe'));

    expect(await screen.findByRole('alert')).toHaveTextContent("'.exe' files cannot be uploaded.");
    expect(screen.queryByRole('button', { name: 'Replace' })).toBeNull();
    await userEvent.click(
      screen.getByRole('button', { name: 'Dismiss the message about tool.exe' }),
    );
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('uploads files dropped on the panel', async () => {
    serve({
      'GET /api/files': () => json(listingOf([])),
      'POST /api/files': (init) => json([{ ...notes, path: uploaded(init).name }], 201),
    });
    render(<FilesPage />);
    const panel = (await screen.findByRole('heading', { name: 'Add files for your agents' }))
      .parentElement as HTMLElement;

    fireEvent.drop(panel, {
      dataTransfer: { files: [new File(['x'], 'dropped.txt')], types: ['Files'] },
    });

    expect(await screen.findByRole('status')).toHaveTextContent('dropped.txt uploaded.');
  });

  it('downloads a file through the API and saves it under its name', async () => {
    serve({
      'GET /api/files': () => json(listingOf([report])),
      'GET /api/files/reports/q3.pdf': () => new Response('%PDF-1.4', { status: 200 }),
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<FilesPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Download q3.pdf' }));

    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe('q3.pdf');
    expect(link.href).toBe('blob:download');
  });

  it('asks before deleting, and deletes only on confirm', async () => {
    const fetchMock = serve({
      'GET /api/files': () => json(listingOf([notes])),
      'DELETE /api/files/notes.txt': () => new Response(null, { status: 204 }),
    });
    render(<FilesPage />);
    const remove = await screen.findByRole('button', { name: 'Delete notes.txt' });

    await userEvent.click(remove);
    const confirm = screen.getByRole('group', { name: 'Confirm delete' });
    expect(within(confirm).getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('group', { name: 'Confirm delete' })).toBeNull();
    expect(remove).toHaveFocus();

    await userEvent.click(remove);
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByRole('status')).toHaveTextContent('notes.txt deleted.');
    expect(await screen.findByText('No files yet')).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(1);
  });

  it('shows a failed delete on the row it concerns', async () => {
    serve({
      'GET /api/files': () => json(listingOf([notes])),
      'DELETE /api/files/notes.txt': () =>
        json({ error: 'server_error', detail: 'An unexpected error occurred.' }, 500),
    });
    render(<FilesPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Delete notes.txt' }));
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('An unexpected error occurred.');
    expect(screen.getByRole('button', { name: 'Delete notes.txt' })).toBeEnabled();
  });

  it('says so when the files cannot be loaded', async () => {
    serve({
      'GET /api/files': () => json({ error: 'server_error', detail: 'Storage is offline.' }, 500),
    });
    render(<FilesPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Storage is offline.');
  });

  it('cancels its requests when it leaves the screen', async () => {
    let signal: AbortSignal | null | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = render(<FilesPage />);

    await screen.findByText('Loading your files…');
    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
