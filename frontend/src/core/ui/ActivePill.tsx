import { motion } from 'motion/react';

interface ActivePillProps {
  /** Shared by every pill in one group, so the pill glides from item to item. */
  layoutId: string;
  className?: string;
}

const SPRING = { type: 'spring', stiffness: 500, damping: 38 } as const;

/**
 * Highlight behind the selected item of a nav, tab list or segmented picker.
 * Render it inside the active item only; the item must be `relative isolate`.
 */
export function ActivePill({ layoutId, className = '' }: ActivePillProps) {
  return (
    <motion.span
      layoutId={layoutId}
      aria-hidden="true"
      transition={SPRING}
      className={`absolute inset-0 -z-10 rounded-[inherit] ${className}`}
    />
  );
}
