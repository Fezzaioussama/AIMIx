import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { downloadFile } from '../api/files';
import { RenderedMarkdown } from './RenderedMarkdown';

vi.mock('../api/files', () => ({ downloadFile: vi.fn() }));

describe('RenderedMarkdown', () => {
  it('renders a sanitised reading document with its headings nested from the base', () => {
    const { container } = render(
      <RenderedMarkdown
        markdown={'# Plan\n\n## Costs\n\n| City | Price |\n|--|--|\n| Paris | 1,900 |'}
        headingBase={4}
        className="mt-5 text-slate-200"
      />,
    );

    const body = container.firstElementChild;
    expect(body).toHaveClass('prose-output', 'prose-document', 'mt-5', 'text-slate-200');
    expect(screen.getByRole('heading', { level: 4, name: 'Plan' })).toHaveAttribute(
      'data-level',
      '1',
    );
    expect(screen.getByRole('heading', { level: 5, name: 'Costs' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Table' })).toHaveAttribute('tabindex', '0');
  });

  it('shows a model’s script as nothing', () => {
    const { container } = render(
      <RenderedMarkdown markdown={'hello <script>alert(1)</script>'} headingBase={3} />,
    );

    expect(container.querySelector('script')).toBeNull();
    expect(container).toHaveTextContent('hello');
  });

  it('shows a picture the text names by workspace path, fetched with the session', async () => {
    vi.mocked(downloadFile).mockResolvedValue(new Blob(['jpeg'], { type: 'image/jpeg' }));

    const { container } = render(
      <RenderedMarkdown markdown="![The hero loaf](images/hero.jpg)" headingBase={3} />,
    );

    await vi.waitFor(() =>
      expect(container.querySelector('img')?.getAttribute('src')).toMatch(/^data:image\/jpeg;/),
    );
    expect(downloadFile).toHaveBeenCalledWith('images/hero.jpg', expect.any(AbortSignal));
  });
});
