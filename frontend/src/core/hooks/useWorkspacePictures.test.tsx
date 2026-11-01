import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { downloadFile } from '../api/files';
import { renderMarkdown } from '../markdown/renderMarkdown';
import { useWorkspacePictures } from './useWorkspacePictures';

vi.mock('../api/files', () => ({ downloadFile: vi.fn() }));

function Rendered({ markdown }: { markdown: string }) {
  const html = renderMarkdown(markdown);
  const pictures = useWorkspacePictures(html);
  return <div ref={pictures} dangerouslySetInnerHTML={{ __html: html }} />;
}

afterEach(() => vi.mocked(downloadFile).mockReset());

describe('useWorkspacePictures', () => {
  it('shows a picture the text names by workspace path, fetched with the session', async () => {
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));

    const { container } = render(<Rendered markdown="![Hero](images/hero.jpg)" />);

    await vi.waitFor(() =>
      expect(container.querySelector('img')?.getAttribute('src')).toMatch(/^data:image\/jpeg;/),
    );
    expect(downloadFile).toHaveBeenCalledWith('images/hero.jpg', expect.any(AbortSignal));
  });

  it('loads the pictures that new text brings', async () => {
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));
    const { rerender } = render(<Rendered markdown="Drawing the picture…" />);
    expect(downloadFile).not.toHaveBeenCalled();

    rerender(<Rendered markdown="![Hero](images/hero.jpg)" />);

    await vi.waitFor(() => expect(downloadFile).toHaveBeenCalledTimes(1));
  });

  it('keeps the alt text when the picture cannot be loaded', async () => {
    vi.mocked(downloadFile).mockRejectedValue(new Error('gone'));

    const { container } = render(<Rendered markdown="![Hero](images/hero.jpg)" />);

    await vi.waitFor(() => expect(downloadFile).toHaveBeenCalled());
    expect(container.querySelector('img')).not.toHaveAttribute('src');
    expect(container.querySelector('img')).toHaveAttribute('alt', 'Hero');
  });

  it('cancels the downloads when the text leaves the screen', () => {
    vi.mocked(downloadFile).mockReturnValue(new Promise(() => {}));

    const { unmount } = render(<Rendered markdown="![Hero](images/hero.jpg)" />);
    const signal = vi.mocked(downloadFile).mock.calls[0][1];
    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
