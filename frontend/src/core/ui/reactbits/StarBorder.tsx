import type { CSSProperties } from 'react';

import { BRAND_HIGHLIGHT } from '../brand';

interface StarBorderProps {
  color?: string;
  /** Seconds for one lap of the border. */
  speed?: number;
}

// A conic gradient spun through the registered --aimix-angle property, masked to a
// 1px ring by `border-mask` (styles.css), so a comet of light laps the edge.
const RING =
  'border-mask absolute inset-0 rounded-[inherit] bg-[conic-gradient(from_var(--aimix-angle),transparent_0%,transparent_62%,var(--star-color)_82%,white_88%,transparent_96%)] motion-safe:animate-orbit';

/**
 * A star of light orbiting its parent's border — adapted from React Bits
 * "StarBorder" (reactbits.dev, see LICENSE.md), re-done in CSS. The parent must
 * be `relative` and rounded; the ring inherits its radius.
 */
export function StarBorder({ color = BRAND_HIGHLIGHT, speed = 4 }: StarBorderProps) {
  const style = { '--star-color': color, animationDuration: `${speed}s` } as CSSProperties;
  return (
    <span aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[inherit]">
      {/* A blurred copy behind the crisp ring makes the comet glow past the edge. */}
      <span className="absolute inset-0 rounded-[inherit] opacity-70 blur-[5px]">
        <span style={style} className={RING} />
      </span>
      <span style={style} className={RING} />
    </span>
  );
}
