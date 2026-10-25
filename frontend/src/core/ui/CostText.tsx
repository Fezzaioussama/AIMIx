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
      <span className="sr-only">{`, ${view.tip}`}</span>
    </span>
  );
}
