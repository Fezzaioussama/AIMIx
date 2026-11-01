/**
 * The motion scale for motion/react, mirroring transitions.dev's tokens so every
 * animated surface shares one rhythm. Durations are in seconds. `EASE_SMOOTH_OUT` is
 * the same curve as `--ease-smooth-out` in styles.css (Tailwind's `ease-smooth-out`),
 * which CSS transitions use.
 */

/** quick: a close or a text swap; fast: an open or an icon swap; medium and slow: panels. */
export const DURATION = { quick: 0.15, fast: 0.25, medium: 0.35, slow: 0.4 } as const;

/** Surfaces opening, closing, rising into place. */
export const EASE_SMOOTH_OUT = [0.22, 1, 0.36, 1] as const;

/** Travel in px: micro for text swapping in place, base for content arriving. */
export const DISTANCE = { micro: 4, base: 8 } as const;

/** The blur a swap passes through, as `filter` values. */
export const BLUR = { small: 'blur(2px)', icon: 'blur(4px)', none: 'blur(0px)' } as const;

/** An icon swapping in its slot: a spring with no overshoot. */
export const ICON_SPRING = { type: 'spring', duration: 0.3, bounce: 0 } as const;
