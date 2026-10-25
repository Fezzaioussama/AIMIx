import type { CostView } from '../usageFormat';

interface CostTextProps {
  view: CostView;
  /** Tight rows: the short words ("Cost unknown") instead of the full ones. */
  compact?: boolean;
  className?: string;
}

/**
 * A cost as plain words. The token counts are a hover away (the title) and are
 * also read out after the cost, so nothing depends on the pointer.
 */
export function CostText({ view, compact = false, className = '' }: CostTextProps) {
  return (
    <span title={view.tip} className={`tabular-nums ${className}`}>
      {compact ? view.short : view.text}
      {/* In brackets, so "(40 out) of $0.0010 limit" cannot be heard as "40 out of $0.0010". */}
      <span className="sr-only">{` (${view.tip})`}</span>
    </span>
  );
}
