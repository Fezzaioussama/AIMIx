import { Link } from 'react-router-dom';

import { LEGAL_LINKS } from '../routes';

/** The legal pages as one row of small links, so every screen reaches them. */
export function LegalLinks({ className = '' }: { className?: string }) {
  return (
    <nav
      aria-label="Legal"
      className={`flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400 ${className}`}
    >
      {LEGAL_LINKS.map((link) => (
        <Link
          key={link.path}
          to={link.path}
          className="transition-colors hover:text-slate-100 focus-visible:outline-2 focus-visible:outline-sky-400"
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}
