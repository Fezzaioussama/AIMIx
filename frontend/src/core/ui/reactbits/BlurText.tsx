import { motion } from 'motion/react';

interface BlurTextProps {
  text: string;
  animateBy?: 'words' | 'letters';
  direction?: 'top' | 'bottom';
  /** Milliseconds between one segment and the next. */
  delay?: number;
  className?: string;
}

const EASE_OUT = [0.33, 1, 0.68, 1] as const;

/**
 * Text that resolves from a blur, segment by segment — adapted from React Bits
 * "BlurText" (reactbits.dev, see LICENSE.md). Screen readers get the plain text
 * once; the animated pieces are hidden from them.
 */
export function BlurText({
  text,
  animateBy = 'words',
  direction = 'top',
  delay = 90,
  className = '',
}: BlurTextProps) {
  const segments = animateBy === 'words' ? text.split(' ') : Array.from(text);
  const offset = direction === 'top' ? -18 : 18;

  // The screen-reader copy is a sibling of the styled span so a `bg-clip-text`
  // className cannot paint its visually hidden glyphs.
  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true" className={`inline-flex flex-wrap ${className}`}>
        {segments.map((segment, index) => (
          <motion.span
            key={`${text}-${index}`}
            className="inline-block whitespace-pre will-change-[transform,filter,opacity]"
            initial={{ filter: 'blur(10px)', opacity: 0, y: offset }}
            animate={{
              filter: ['blur(10px)', 'blur(4px)', 'blur(0px)'],
              opacity: [0, 0.5, 1],
              y: [offset, offset * -0.15, 0],
            }}
            transition={{
              duration: 0.7,
              times: [0, 0.5, 1],
              delay: (index * delay) / 1000,
              ease: EASE_OUT,
            }}
          >
            {animateBy === 'words' && index < segments.length - 1 ? `${segment} ` : segment}
          </motion.span>
        ))}
      </span>
    </>
  );
}
