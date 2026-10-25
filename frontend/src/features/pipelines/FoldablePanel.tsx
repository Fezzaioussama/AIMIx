import { ChevronDown } from 'lucide-react';
import type { ReactNode } from 'react';

interface PanelToggleProps {
  /** Ties the bar to its body (`${id}-title`, `${id}-body`). */
  id: string;
  /** The panel title's heading level. */
  level: 2 | 3;
  icon: ReactNode;
  title: string;
  open: boolean;
  onToggle: () => void;
}

/** The bar that folds and unfolds a panel: a heading holding one button, its title and a chevron. */
export function PanelToggle({ id, level, icon, title, open, onToggle }: PanelToggleProps) {
  const Heading = level === 2 ? 'h2' : 'h3';
  return (
    <Heading id={`${id}-title`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={onToggle}
        className="flex w-full cursor-pointer items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-sm font-semibold text-slate-100 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 sm:px-5"
      >
        {icon}
        <span className="flex-1">{title}</span>
        <ChevronDown
          aria-hidden="true"
          className={`size-4 shrink-0 text-slate-400 transition-transform duration-300 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
        />
      </button>
    </Heading>
  );
}

/** Opens by animating its grid row; `inert` keeps folded content out of reach. */
export function Foldable({
  id,
  open,
  children,
}: {
  id: string;
  open: boolean;
  children: ReactNode;
}) {
  return (
    <div
      id={id}
      inert={!open}
      className={`grid transition-[grid-template-rows] duration-300 motion-reduce:transition-none ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
    >
      <div className="min-w-0 overflow-hidden">
        <div className="px-4 pb-5 sm:px-5">{children}</div>
      </div>
    </div>
  );
}
