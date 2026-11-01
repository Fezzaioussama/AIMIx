import { useMemo } from 'react';

import { useWorkspacePictures } from '../hooks/useWorkspacePictures';
import { renderDocument } from './renderMarkdown';

interface RenderedMarkdownProps {
  markdown: string;
  /** The level the text's own `#` headings start at, so they nest under the page's. */
  headingBase: number;
  className?: string;
}

/**
 * A model's Markdown as a sanitised reading document (renderDocument), with the pictures
 * it names by workspace path loaded (useWorkspacePictures).
 */
export function RenderedMarkdown({ markdown, headingBase, className = '' }: RenderedMarkdownProps) {
  const html = useMemo(() => renderDocument(markdown, headingBase), [markdown, headingBase]);
  const pictures = useWorkspacePictures(html);
  return (
    <div
      ref={pictures}
      className={`prose-output prose-document ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
