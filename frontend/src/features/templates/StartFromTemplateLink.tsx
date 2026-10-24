import { LayoutTemplate } from 'lucide-react';
import { Link } from 'react-router-dom';

/** A quiet way into the template gallery from screens where a user starts from nothing. */
export function StartFromTemplateLink({ className = '' }: { className?: string }) {
  return (
    <Link
      to="/templates"
      className={`inline-flex items-center gap-1.5 rounded text-sm font-medium text-sky-300 transition-colors hover:text-sky-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 ${className}`}
    >
      <LayoutTemplate aria-hidden="true" className="size-4" />
      Start from a template
    </Link>
  );
}
