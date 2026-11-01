import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import { BLUR, DISTANCE, FADE, QUICK_EXIT } from './motionTokens';

interface SwapTextProps {
  text: string;
  className?: string;
}

// The old words rise out through a 2px blur, then the new ones rise in from below.
const MOVING = {
  initial: { opacity: 0, y: DISTANCE.micro, filter: BLUR.small },
  animate: { opacity: 1, y: 0, filter: BLUR.none },
  exit: { opacity: 0, y: -DISTANCE.micro, filter: BLUR.small },
};

/**
 * Text that changes in place: a status heading, a slot's state words. Nothing moves
 * on first render; each later change swaps the words (text states swap, 150ms).
 */
export function SwapText({ text, className = '' }: SwapTextProps) {
  // Reduced motion keeps only the cross-fade.
  const swap = useReducedMotion() ? FADE : MOVING;
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={text}
        className={`inline-block ${className}`}
        {...swap}
        transition={QUICK_EXIT}
      >
        {text}
      </motion.span>
    </AnimatePresence>
  );
}
