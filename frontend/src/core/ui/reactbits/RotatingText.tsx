import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

interface RotatingTextProps {
  texts: readonly string[];
  /** Milliseconds each text stays on screen. */
  interval?: number;
  /**
   * Gradient stops spread across each phrase, one solid colour per letter. Use this,
   * not `bg-clip-text`: Chrome clips to the letters' untransformed positions, so the
   * roll would be invisible.
   */
  colors?: readonly string[];
  className?: string;
}

const SPRING = { type: 'spring', damping: 30, stiffness: 400 } as const;

/** The colour at `t` (0..1) along `colors`, mixed in OKLCH like a CSS gradient. */
function colorAt(colors: readonly string[], t: number): string | undefined {
  if (colors.length < 2) return colors[0];
  const scaled = t * (colors.length - 1);
  const index = Math.min(Math.floor(scaled), colors.length - 2);
  const share = Math.round((scaled - index) * 100);
  return `color-mix(in oklch, ${colors[index + 1]} ${share}%, ${colors[index]})`;
}

/**
 * Cycles through `texts`, rolling each one in letter by letter — adapted from
 * React Bits "RotatingText" (reactbits.dev, see LICENSE.md). Screen readers hear
 * the whole list once instead of a change every few seconds.
 */
export function RotatingText({
  texts,
  interval = 2600,
  colors = [],
  className = '',
}: RotatingTextProps) {
  const [index, setIndex] = useState(0);
  const current = texts[index % texts.length] ?? '';

  useEffect(() => {
    if (texts.length < 2) return undefined;
    const timer = window.setInterval(
      () => setIndex((value) => (value + 1) % texts.length),
      interval,
    );
    return () => window.clearInterval(timer);
  }, [texts.length, interval]);

  // The screen-reader copy is a sibling, not a child, so styling the visible text
  // can never leak onto it.
  return (
    <>
      <span className="sr-only">{texts.join(', ')}</span>
      <motion.span
        layout
        transition={SPRING}
        aria-hidden="true"
        className={`relative inline-flex overflow-hidden ${className}`}
      >
        <AnimatePresence mode="wait" initial={false}>
          <RollingLetters key={current} text={current} colors={colors} />
        </AnimatePresence>
      </motion.span>
    </>
  );
}

/** One phrase whose letters roll in from below, staggered, and roll out upwards. */
function RollingLetters({ text, colors }: { text: string; colors: readonly string[] }) {
  const letters = Array.from(text);
  return (
    <span className="inline-flex">
      {letters.map((char, position) => (
        <motion.span
          key={position}
          className="inline-block whitespace-pre"
          style={{ color: colorAt(colors, position / Math.max(letters.length - 1, 1)) }}
          initial={{ y: '100%', opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: '-120%', opacity: 0 }}
          transition={{ ...SPRING, delay: position * 0.025 }}
        >
          {char}
        </motion.span>
      ))}
    </span>
  );
}
