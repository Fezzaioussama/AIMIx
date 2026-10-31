/** One legal document: Markdown in French, with `{{fact}}` for each operator fact. */
export interface LegalDocument {
  title: string;
  /** When its text last changed, as it is shown. */
  updated: string;
  markdown: string;
}
