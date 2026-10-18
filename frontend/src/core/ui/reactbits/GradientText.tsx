import type { CSSProperties, ReactNode } from 'react';

import { BRAND_COLORS } from '../brand';

interface GradientTextProps {
  children: ReactNode;
  colors?: readonly string[];
  /** Seconds for one full sweep of the gradient. */
  speed?: number;
  className?: string;
}

/**
 * Text filled with a slowly panning gradient, adapted from React Bits
 * "GradientText" (reactbits.dev, see LICENSE.md). CSS-only; it holds still under
 * prefers-reduced-motion.
 */
export function GradientText({
  children,
  colors = BRAND_COLORS,
  speed = 8,
  className = '',
}: GradientTextProps) {
  // Repeat the first colour at the end so the loop has no seam.
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(90deg, ${[...colors, colors[0]].join(', ')})`,
    animationDuration: `${speed}s`,
  };
  return (
    <span
      style={style}
      className={`inline-block bg-[length:300%_100%] bg-clip-text text-transparent motion-safe:animate-gradient-pan ${className}`}
    >
      {children}
    </span>
  );
}
