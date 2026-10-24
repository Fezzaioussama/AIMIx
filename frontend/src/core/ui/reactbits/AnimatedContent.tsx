import { motion } from 'motion/react';
import type { ReactNode } from 'react';

interface AnimatedContentProps {
  children: ReactNode;
  /** Pixels the content travels while it fades in. */
  distance?: number;
  direction?: 'vertical' | 'horizontal';
  /** Come from above / the left instead of below / the right. */
  reverse?: boolean;
  /** Seconds to wait — pass `index * step` to stagger a list. */
  delay?: number;
  duration?: number;
  /** Starting scale; 1 keeps the size fixed. */
  scale?: number;
  /** Wait until the content scrolls into view (once) instead of animating on mount. */
  whenInView?: boolean;
  className?: string;
}

const EASE_OUT_EXPO = [0.16, 1, 0.3, 1] as const;

/**
 * Fades and slides its children into place on mount (or on first scroll into view
 * with `whenInView`) — adapted from React Bits
 * "AnimatedContent" (reactbits.dev, see LICENSE.md), driven by motion instead of
 * GSAP so the app ships one animation engine.
 */
export function AnimatedContent({
  children,
  distance = 24,
  direction = 'vertical',
  reverse = false,
  delay = 0,
  duration = 0.6,
  scale = 1,
  whenInView = false,
  className,
}: AnimatedContentProps) {
  const offset = reverse ? -distance : distance;
  const initial =
    direction === 'vertical' ? { opacity: 0, y: offset, scale } : { opacity: 0, x: offset, scale };
  const target = { opacity: 1, x: 0, y: 0, scale: 1 };

  return (
    <motion.div
      className={className}
      initial={initial}
      animate={whenInView ? undefined : target}
      whileInView={whenInView ? target : undefined}
      viewport={whenInView ? { once: true, margin: '0px 0px -80px 0px' } : undefined}
      transition={{ duration, delay, ease: EASE_OUT_EXPO }}
    >
      {children}
    </motion.div>
  );
}
