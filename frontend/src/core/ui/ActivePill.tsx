import { motion } from 'motion/react';

interface ActivePillProps {
  /** Shared by every pill in one group, so the pill glides from item to item. */
  layoutId: string;
  className?: string;
  /**
   * Set it to the selected item's key when the group itself can move while it
   * stays on screen, e.g. tabs under live content: the pill then glides only
   * when the selection changes (the keys differ), not after the whole group
   * whenever it shifts. Every item must pass its own key.
   */
  layoutDependency?: string | number;
}

const SPRING = { type: 'spring', stiffness: 500, damping: 38 } as const;

/**
 * Highlight behind the selected item of a nav, tab list or segmented picker.
 * Render it inside the active item only; the item must be `relative isolate`.
 */
export function ActivePill({ layoutId, className = '', layoutDependency }: ActivePillProps) {
  return (
    <motion.span
      layoutId={layoutId}
      layoutDependency={layoutDependency}
      aria-hidden="true"
      transition={SPRING}
      className={`absolute inset-0 -z-10 rounded-[inherit] ${className}`}
    />
  );
}
