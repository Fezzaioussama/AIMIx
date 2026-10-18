import type { CSSProperties, HTMLAttributes, PointerEvent } from 'react';

type Variant = 'plain' | 'glass' | 'highlighted';

interface SpotlightCardProps extends HTMLAttributes<HTMLElement> {
  spotlightColor?: string;
  /** Render as a <section> (with its own aria label) instead of a <div>. */
  as?: 'div' | 'section';
  /** `glass` blurs what is behind it; `highlighted` marks the selected card. */
  variant?: Variant;
}

const SURFACE =
  'group/spot relative isolate overflow-hidden rounded-2xl border transition-[border-color,box-shadow] duration-500';

// Border, fill and shadow live here, not in callers' classes, so nothing fights over them.
const VARIANTS: Record<Variant, string> = {
  plain: 'border-white/10 bg-slate-900/60 shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]',
  glass:
    'border-white/10 bg-slate-950/70 shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)] backdrop-blur-xl',
  highlighted: 'border-sky-400/40 bg-slate-900/60 shadow-[0_0_40px_-18px_rgba(56,189,248,0.7)]',
};

// The light follows the pointer through CSS variables, so moving never re-renders React.
const GLOW =
  'pointer-events-none absolute inset-0 -z-10 rounded-[inherit] bg-[radial-gradient(circle_320px_at_var(--spot-x,50%)_var(--spot-y,0%),var(--spot-color),transparent_75%)] opacity-0 transition-opacity duration-500 group-hover/spot:opacity-100 group-focus-within/spot:opacity-100';

const EDGE =
  'border-mask pointer-events-none absolute inset-0 rounded-[inherit] bg-[radial-gradient(circle_180px_at_var(--spot-x,50%)_var(--spot-y,0%),rgba(255,255,255,0.4),transparent_70%)] opacity-0 transition-opacity duration-500 group-hover/spot:opacity-100';

/**
 * Glass card lit by a soft spotlight under the cursor, with a matching glint on
 * its border — adapted from React Bits "SpotlightCard" (reactbits.dev, see LICENSE.md).
 */
export function SpotlightCard({
  children,
  className = '',
  spotlightColor = 'rgba(56, 189, 248, 0.12)',
  as: Tag = 'div',
  variant = 'plain',
  style,
  ...rest
}: SpotlightCardProps) {
  function handlePointerMove(event: PointerEvent<HTMLElement>) {
    const card = event.currentTarget;
    const rect = card.getBoundingClientRect();
    card.style.setProperty('--spot-x', `${event.clientX - rect.left}px`);
    card.style.setProperty('--spot-y', `${event.clientY - rect.top}px`);
  }

  return (
    <Tag
      {...rest}
      onPointerMove={handlePointerMove}
      style={{ '--spot-color': spotlightColor, ...style } as CSSProperties}
      className={`${SURFACE} ${VARIANTS[variant]} ${className}`}
    >
      <span aria-hidden="true" className={GLOW} />
      <span aria-hidden="true" className={EDGE} />
      {children}
    </Tag>
  );
}
