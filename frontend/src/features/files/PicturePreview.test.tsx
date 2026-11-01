import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { downloadFile } from '../../core/api/files';
import { PicturePreview } from './PicturePreview';

vi.mock('../../core/api/files', () => ({ downloadFile: vi.fn() }));

describe('PicturePreview', () => {
  afterEach(() => vi.clearAllMocks());

  it('shows the picture, fetched with the session, with the caller’s sizing', async () => {
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));

    const { container } = render(<PicturePreview path="images/hero.jpg" className="max-h-80" />);

    await vi.waitFor(() => expect(container.querySelector('img')).not.toBeNull());
    const image = container.querySelector('img');
    expect(image?.getAttribute('src')).toMatch(/^data:image\/jpeg;/);
    // The file's name follows it, so it is not announced again.
    expect(image).toHaveAttribute('alt', '');
    expect(image).toHaveClass('outline-white/10', 'max-h-80');
    expect(downloadFile).toHaveBeenCalledWith('images/hero.jpg', expect.any(AbortSignal));
  });

  it('shows nothing when the picture cannot be loaded', async () => {
    vi.mocked(downloadFile).mockRejectedValue(new Error('offline'));

    const { container } = render(<PicturePreview path="images/hero.jpg" />);

    await vi.waitFor(() => expect(downloadFile).toHaveBeenCalled());
    expect(container.querySelector('img')).toBeNull();
  });
});
