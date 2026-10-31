import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { LEGAL_NOTICE_PATH, PRIVACY_PATH, TERMS_PATH, type LegalPath } from '../../core/routes';
import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import { LegalLinks } from '../../core/ui/LegalLinks';
import { ScrollToTop } from '../../core/ui/ScrollToTop';
import { LEGAL_NOTICE } from './documents/legalNotice';
import { PRIVACY_POLICY } from './documents/privacyPolicy';
import { TERMS } from './documents/terms';
import type { LegalDocument } from './documents/types';
import { fillFacts, missingFacts } from './fillFacts';
import { OPERATOR } from './operator';

/** Each document by its route. */
const DOCUMENTS: Record<LegalPath, LegalDocument> = {
  [LEGAL_NOTICE_PATH]: LEGAL_NOTICE,
  [PRIVACY_PATH]: PRIVACY_POLICY,
  [TERMS_PATH]: TERMS,
};

/** While a fact is missing, the page says it is a draft rather than pass for a final text. */
function DraftNote() {
  return (
    <p
      role="note"
      className="mt-4 rounded-lg border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100"
    >
      Version provisoire : les informations marquées « à compléter » doivent encore être fournies
      par l'éditeur.
    </p>
  );
}

/**
 * One legal page (/legal, /privacy, /terms), public like the landing page. Its route
 * says which (`path`), never the address typed: the router also matches `/privacy/`
 * and `/PRIVACY`. Its text is ours, but it still goes through the one Markdown
 * sanitiser (AGENTS.md §8).
 */
export function LegalPage({ path }: { path: LegalPath }) {
  const page = DOCUMENTS[path];
  const html = useMemo(() => renderMarkdown(fillFacts(page.markdown, OPERATOR)), [page]);

  return (
    <div className="min-h-screen px-4 py-10 text-slate-50">
      <ScrollToTop />
      <div className="mx-auto max-w-3xl">
        <header className="mb-10 flex flex-wrap items-center justify-between gap-4">
          <Link to="/" aria-label="AIMIx home">
            <img src="/logo.png" alt="AIMIx" className="h-10 w-auto" />
          </Link>
          <LegalLinks />
        </header>
        <article lang="fr">
          <h1 className="text-3xl font-extrabold tracking-tight">{page.title}</h1>
          <p className="mt-2 text-sm text-slate-400">Dernière mise à jour : {page.updated}</p>
          {missingFacts(OPERATOR).length > 0 && <DraftNote />}
          <div className="prose-output mt-8" dangerouslySetInnerHTML={{ __html: html }} />
        </article>
      </div>
    </div>
  );
}
