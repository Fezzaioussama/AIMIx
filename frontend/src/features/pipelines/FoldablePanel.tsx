import { ChevronDown } from 'lucide-react';
import type { ReactNode } from 'react';

import { FOCUS_RING, TOUCH } from '../../core/ui/focus';

/** A disclosure's chevron: it flips upside down while its panel is open. */
function Chevron({ open, className = '' }: { open: boolean; className?: string }) {
  return (
    <ChevronDown
      aria-hidden="true"
      className={`size-4 shrink-0 transition-transform duration-250 ease-smooth-out motion-reduce:transition-none ${open ? '-scale-y-100' : ''} ${className}`}
    />
  );
}

interface PanelToggleProps {
  /** Ties the bar to its body (`${id}-title`, `${id}-body`). */
  id: string;
  /** The panel title's heading level. */
  level: 2 | 3;
  icon: ReactNode;
  title: string;
  /** A short fact beside the title, e.g. "4 agents · 3 stages". */
  summary?: string;
  open: boolean;
  onToggle: () => void;
}

/** The bar that folds and unfolds a panel: a heading holding one button, its title and a chevron. */
export function PanelToggle({ id, level, icon, title, summary, open, onToggle }: PanelToggleProps) {
  const Heading = level === 2 ? 'h2' : 'h3';
  return (
    <Heading id={`${id}-title`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-body`}
        onClick={onToggle}
        className={`flex w-full cursor-pointer items-center gap-3 rounded-2xl px-4 py-3.5 text-left text-sm font-semibold text-slate-100 transition-colors hover:text-white sm:px-5 ${FOCUS_RING}`}
      >
        {icon}
        <span className="flex-1">{title}</span>
        {summary && (
          <span className="text-xs font-normal text-slate-400 tabular-nums">
            <span className="sr-only">,</span> {summary}
          </span>
        )}
        <Chevron open={open} className="text-slate-400" />
      </button>
    </Heading>
  );
}

/** Open and close times (§5 M7): a small fold for a line or two, a large one for a panel. */
const TIMING = {
  small: { open: 'duration-250', close: 'duration-150' },
  large: { open: 'duration-350', close: 'duration-250' },
} as const;

interface FoldableProps {
  id: string;
  open: boolean;
  children: ReactNode;
  size?: keyof typeof TIMING;
  /** The body's padding; the default suits a panel under a PanelToggle. */
  bodyClassName?: string;
}

/**
 * Opens by animating its grid row while its body fades and sharpens in; `inert`
 * keeps folded content out of reach.
 */
export function Foldable({
  id,
  open,
  children,
  size = 'large',
  bodyClassName = 'px-4 pb-5 sm:px-5',
}: FoldableProps) {
  const timing = `${open ? TIMING[size].open : TIMING[size].close} ease-smooth-out motion-reduce:transition-none`;
  return (
    <div
      id={id}
      inert={!open}
      className={`grid transition-[grid-template-rows] ${timing} ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
    >
      <div className="min-w-0 overflow-hidden">
        <div
          className={`transition-[opacity,filter] ${timing} ${open ? 'opacity-100' : 'opacity-0 blur-[2px]'} ${bodyClassName}`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

interface DisclosureButtonProps {
  open: boolean;
  /** The id of the Foldable it opens. */
  controls: string;
  label: string;
  onToggle: () => void;
  /** So a jump can move focus back to it, e.g. from a "Hide …" button at the end of its panel. */
  id?: string;
}

/** An inline text button that opens a Foldable: "Read the full check". */
export function DisclosureButton({ open, controls, label, onToggle, id }: DisclosureButtonProps) {
  return (
    <button
      id={id}
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
      className={`inline-flex cursor-pointer items-center gap-1 rounded-md text-sm font-medium text-sky-300 transition-colors duration-150 ease-out hover:text-sky-200 ${TOUCH} ${FOCUS_RING}`}
    >
      {label}
      <Chevron open={open} />
    </button>
  );
}
