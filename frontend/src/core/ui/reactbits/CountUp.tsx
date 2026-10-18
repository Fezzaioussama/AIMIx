import { animate, useReducedMotion } from 'motion/react';
import { useLayoutEffect, useRef } from 'react';

interface CountUpProps {
  to: number;
  from?: number;
  /** Seconds the count takes. */
  duration?: number;
  decimals?: number;
  className?: string;
}

/**
 * A number that counts to its value — adapted from React Bits "CountUp"
 * (reactbits.dev, see LICENSE.md). A later `to` counts on from the number shown.
 * The text is written straight to the DOM each frame, so counting never re-renders.
 */
export function CountUp({
  to,
  from = 0,
  duration = 1.2,
  decimals = 0,
  className = '',
}: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef(from);
  const reduceMotion = useReducedMotion();

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const write = (value: number) => {
      shown.current = value;
      element.textContent = value.toFixed(decimals);
    };
    if (reduceMotion) {
      write(to);
      return undefined;
    }
    write(shown.current);
    const controls = animate(shown.current, to, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: write,
    });
    return () => controls.stop();
  }, [to, duration, decimals, reduceMotion]);

  return <span ref={ref} className={`tabular-nums ${className}`} />;
}
