import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { downloadFile } from '../../core/api/files';
import type { WorkspaceFile } from '../../core/api/types';
import { RecentFiles } from './RecentFiles';

vi.mock('../../core/api/files', () => ({ downloadFile: vi.fn() }));
vi.mock('./useRecentFiles', () => ({
  useRecentFiles: () => ({ files: FILES, error: '' }),
}));

const file = (path: string, type: string): WorkspaceFile => ({
  path,
  size: 640_000,
  modified_at: '2026-10-31T10:00:00Z',
  type,
});
const FILES = [file('images/hero.jpg', 'jpg'), file('launch-plan.pdf', 'pdf')];

describe('RecentFiles', () => {
  it('shows a picture above its name, fetched with the session', async () => {
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));

    const { container } = render(
      <MemoryRouter>
        <RecentFiles refreshKey="none-ended" />
      </MemoryRouter>,
    );

    expect(await screen.findByText('hero.jpg')).toBeInTheDocument();
    await vi.waitFor(() => expect(container.querySelector('img')).not.toBeNull());
    expect(container.querySelector('img')?.getAttribute('src')).toMatch(/^data:image\/jpeg;/);
    expect(container.querySelectorAll('img')).toHaveLength(1);
    expect(downloadFile).toHaveBeenCalledWith('images/hero.jpg', expect.any(AbortSignal));
  });
});
