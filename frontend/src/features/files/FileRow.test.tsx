import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { WorkspaceFile } from '../../core/api/types';
import { FileRow } from './FileRow';

const report: WorkspaceFile = {
  path: 'reports/q3.pdf',
  size: 640_000,
  modified_at: '2026-10-31T10:00:00Z',
  type: 'pdf',
};

function renderRow(props: Partial<Parameters<typeof FileRow>[0]> = {}) {
  const onDownload = vi.fn();
  render(
    <ul>
      <FileRow file={report} action={undefined} error="" onDownload={onDownload} {...props} />
    </ul>,
  );
  return { onDownload };
}

describe('FileRow', () => {
  it('offers only a download when no delete is given', async () => {
    const { onDownload } = renderRow();

    await userEvent.click(screen.getByRole('button', { name: 'Download q3.pdf' }));

    expect(onDownload).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: 'Delete q3.pdf' })).not.toBeInTheDocument();
  });

  it('asks before deleting when a delete is given', async () => {
    const onDelete = vi.fn();
    renderRow({ onDelete });

    await userEvent.click(screen.getByRole('button', { name: 'Delete q3.pdf' }));
    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(onDelete).toHaveBeenCalledOnce();
  });

  it('shows a preview above the file’s name', () => {
    renderRow({ preview: <img alt="" data-testid="preview" /> });

    const preview = screen.getByTestId('preview');
    const name = screen.getByText('q3.pdf');
    expect(preview.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('gives its buttons a finger-sized target on touch screens', () => {
    renderRow({ onDelete: vi.fn() });

    expect(screen.getByRole('button', { name: 'Download q3.pdf' })).toHaveClass(
      'size-9',
      'pointer-coarse:size-11',
    );
  });

  it('says why its last action failed', () => {
    renderRow({ error: 'Could not download the file.' });

    expect(screen.getByRole('alert')).toHaveTextContent('Could not download the file.');
  });
});
