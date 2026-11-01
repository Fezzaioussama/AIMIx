import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { downloadFile, listFiles } from '../../../core/api/files';
import type { FileListing, Run, WorkspaceFile } from '../../../core/api/types';
import { saveBlob } from '../../../core/saveBlob';
import { ENDED, TEAM, defined, runOf, teamRun, type StepState } from './reportTestData';
import { RunFiles } from './RunFiles';

vi.mock('../../../core/api/files', () => ({ listFiles: vi.fn(), downloadFile: vi.fn() }));
vi.mock('../../../core/saveBlob', () => ({ saveBlob: vi.fn() }));

beforeAll(() => {
  MotionGlobalConfig.skipAnimations = true;
});
afterAll(() => {
  MotionGlobalConfig.skipAnimations = false;
});
beforeEach(() => {
  vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));
});
afterEach(() => vi.clearAllMocks());

const file = (path: string, type: string, modified: string): WorkspaceFile => ({
  path,
  size: 640_000,
  modified_at: modified,
  type,
});

function listing(files: WorkspaceFile[]): FileListing {
  return { files, used_bytes: 0, quota_bytes: 1, max_file_bytes: 1, allowed_extensions: [] };
}

// The run worked from 10:00:00 to 10:04:54 (ENDED); its window has 2 s of slack each way.
const BRIEF = file('loop/brief.pdf', 'pdf', '2026-10-24T10:03:00Z');
const HERO = file('images/hero.jpg', 'jpg', '2026-10-24T10:01:00Z');
const EARLIER = file('notes.txt', 'txt', '2026-10-23T09:00:00Z');
const LATER = file('later.md', 'md', '2026-10-24T10:04:57Z');

const DONE: StepState[] = [
  ['succeeded'],
  ['succeeded'],
  ['succeeded'],
  ['succeeded', { verdict: 'pass' }],
];

function finished(): Run {
  return teamRun(DONE, { status: 'succeeded', ...ENDED });
}

function renderFiles(run: Run) {
  const files = (shown: Run) => (
    <MemoryRouter>
      <RunFiles run={shown} level={3} />
    </MemoryRouter>
  );
  const view = render(files(run));
  return { ...view, poll: (next: Run) => view.rerender(files(next)) };
}

function section(): HTMLElement {
  return screen.getByRole('region', { name: 'Saved during this run' });
}

describe('RunFiles', () => {
  it('lists only the files saved while the run worked, pictures first', async () => {
    vi.mocked(listFiles).mockResolvedValue(listing([LATER, BRIEF, HERO, EARLIER]));

    renderFiles(finished());

    expect(
      await screen.findByRole('heading', { level: 3, name: 'Saved during this run' }),
    ).toBeInTheDocument();
    expect(
      within(section()).getByText('Files saved to your workspace while this run worked.'),
    ).toBeInTheDocument();
    const names = within(section())
      .getAllByRole('listitem')
      .map((row) => row.querySelector('p')?.textContent);
    expect(names).toEqual(['hero.jpg', 'brief.pdf']);
    expect(within(section()).getByRole('link', { name: /^All files/ })).toHaveAttribute(
      'href',
      '/files',
    );
    // Download only: a file is deleted from the Files page.
    expect(within(section()).queryByRole('button', { name: /Delete/ })).toBeNull();
  });

  it('shows a picture whole above its name, fetched with the session', async () => {
    vi.mocked(listFiles).mockResolvedValue(listing([HERO]));

    const { container } = renderFiles(finished());

    expect(await screen.findByText('hero.jpg')).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector('img')).not.toBeNull());
    const picture = container.querySelector('img') as HTMLImageElement;
    expect(picture.getAttribute('src')).toMatch(/^data:image\/jpeg;/);
    expect(picture).toHaveAttribute('alt', '');
    expect(picture).toHaveClass('object-contain', 'max-h-80');
    expect(downloadFile).toHaveBeenCalledWith('images/hero.jpg', expect.any(AbortSignal));
    // Above its name, in the same row.
    const row = screen.getByText('hero.jpg').closest('li') as HTMLElement;
    expect(row.firstElementChild).toBe(picture);
  });

  it('shows nothing when no file was saved while the run worked', async () => {
    vi.mocked(listFiles).mockResolvedValue(listing([EARLIER, LATER]));

    const { container } = renderFiles(finished());

    await waitFor(() => expect(listFiles).toHaveBeenCalled());
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing, and no error, when the files cannot be listed', async () => {
    vi.mocked(listFiles).mockRejectedValue(new Error('Server error'));

    const { container } = renderFiles(finished());

    await waitFor(() => expect(listFiles).toHaveBeenCalled());
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('treats an answer it cannot read as a failed load', async () => {
    vi.mocked(listFiles).mockResolvedValue({} as FileListing);

    const { container } = renderFiles(finished());

    await waitFor(() => expect(listFiles).toHaveBeenCalled());
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it('asks nothing of the server when no agent may save a file', async () => {
    const readers = TEAM.map((step) => ({ ...step, allowed_tools: ['web_search'] }));

    renderFiles(runOf(readers, DONE, { status: 'succeeded', ...ENDED }));

    await Promise.resolve();
    expect(listFiles).not.toHaveBeenCalled();
  });

  it('looks again when a step finishes, keeping the list until the new one comes', async () => {
    const saver = [defined(1, 1, 'Research', { allowed_tools: ['save_artifact'] })];
    vi.mocked(listFiles).mockResolvedValue(listing([HERO]));
    const { poll } = renderFiles(runOf(saver, [['running']]));
    expect(await screen.findByText('hero.jpg')).toBeInTheDocument();
    let answer: (files: FileListing) => void = () => undefined;
    vi.mocked(listFiles).mockReturnValue(new Promise((resolve) => (answer = resolve)));

    poll(runOf(saver, [['succeeded']]));

    await waitFor(() => expect(listFiles).toHaveBeenCalledTimes(2));
    expect(screen.getByText('hero.jpg')).toBeInTheDocument();
    answer(listing([HERO, BRIEF]));
    expect(await screen.findByText('brief.pdf')).toBeInTheDocument();
  });

  it('downloads a file under its own name, and says so on its row when that fails', async () => {
    const user = userEvent.setup();
    vi.mocked(listFiles).mockResolvedValue(listing([BRIEF]));
    const pdf = new Blob(['pdf'], { type: 'application/pdf' });
    vi.mocked(downloadFile).mockResolvedValueOnce(pdf);
    renderFiles(finished());

    await user.click(await screen.findByRole('button', { name: 'Download brief.pdf' }));

    expect(downloadFile).toHaveBeenCalledWith('loop/brief.pdf', expect.any(AbortSignal));
    await waitFor(() => expect(saveBlob).toHaveBeenCalledWith(pdf, 'brief.pdf'));

    vi.mocked(downloadFile).mockRejectedValueOnce(new Error('Server error'));
    await user.click(screen.getByRole('button', { name: 'Download brief.pdf' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not download the file.');
    expect(screen.getByRole('button', { name: 'Download brief.pdf' })).toBeEnabled();
  });
});
