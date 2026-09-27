import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * Model output is untrusted text, so it is sanitised after Markdown rendering.
 * (The previous Angular code called bypassSecurityTrustHtml, which skipped
 * sanitisation altogether.) Shared by chat and pipeline results (§3).
 */
export function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false });
  return DOMPurify.sanitize(html);
}
