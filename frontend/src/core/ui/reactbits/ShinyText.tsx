import type { ReactNode } from 'react';

interface ShinyTextProps {
  children: ReactNode;
  /** Seconds for the highlight to cross the text once. */
  speed?: number;
  className?: string;
}

/**
 * A highlight band that sweeps across the text, adapted from React Bits "ShinyText"
 * (reactbits.dev, see LICENSE.md). Give it a semi-transparent text colour
 * (e.g. `text-sky-300/70`) — the band shows through the fill. CSS-only.
 */
export function ShinyText({ children, speed = 3, className = '' }: ShinyTextProps) {
  return (
    <span
      style={{ animationDuration: `${speed}s` }}
      className={`inline-block bg-[linear-gradient(110deg,transparent_40%,rgba(255,255,255,0.85)_50%,transparent_60%)] bg-[length:250%_100%] bg-clip-text motion-safe:animate-shine ${className}`}
    >
      {children}
    </span>
  );
}
