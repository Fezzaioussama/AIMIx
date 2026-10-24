import { Link } from 'react-router-dom';

import { FOOTER_COLUMNS, RELEASE_STAGE } from './content/site';
import type { FooterLink } from './content/site';

const LINK =
  'inline-flex items-center gap-1 text-sm text-slate-400 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-sky-400';

/** An in-page anchor or an app route — each needs a different element. */
function FooterAnchor({ link }: { link: FooterLink }) {
  if (link.href.startsWith('#')) {
    return (
      <a href={link.href} className={LINK}>
        {link.label}
      </a>
    );
  }
  return (
    <Link to={link.href} className={LINK}>
      {link.label}
    </Link>
  );
}

export function LandingFooter() {
  return (
    <footer className="border-t border-white/[0.07] px-4 py-14">
      <div className="mx-auto grid max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr]">
        <div>
          <img src="/logo.png" alt="AIMIx" className="h-14 w-auto" />
          <p className="mt-4 max-w-xs text-sm text-slate-400">
            Design, coordinate, and run multi-agent workflows.
          </p>
        </div>
        {FOOTER_COLUMNS.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <h3 className="text-sm font-semibold text-white">{column.title}</h3>
            <ul className="mt-4 space-y-3">
              {column.links.map((link) => (
                <li key={link.label}>
                  <FooterAnchor link={link} />
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <p className="mx-auto mt-12 max-w-6xl border-t border-white/[0.07] pt-6 text-xs text-slate-400">
        © {new Date().getFullYear()} AIMIx · {RELEASE_STAGE} version
      </p>
    </footer>
  );
}
