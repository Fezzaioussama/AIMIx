import type { ButtonHTMLAttributes } from 'react';

import { ClickSpark } from './reactbits/ClickSpark';
import { StarBorder } from './reactbits/StarBorder';
import { Spinner } from './Spinner';

interface GlowButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Shows a spinner and blocks clicks; the caller's label should say what is happening. */
  busy?: boolean;
  size?: GlowSize;
  /** Stretch to the container's width. */
  block?: boolean;
}

export type GlowSize = 'sm' | 'md' | 'lg';

/** Padding and type size for the app's buttons; secondary buttons borrow it to line up. */
export const BUTTON_SIZES: Record<GlowSize, string> = {
  sm: 'px-4 py-2 text-sm',
  md: 'px-6 py-3 text-sm',
  lg: 'px-8 py-4 text-base',
};

const BASE =
  'relative isolate inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[linear-gradient(110deg,#0891b2_0%,#4f46e5_48%,#c026d3_100%)] bg-[length:180%_100%] bg-left font-semibold text-white shadow-[0_10px_34px_-12px_rgba(79,70,229,0.9)] transition-[background-position,transform,box-shadow] duration-500 not-disabled:hover:-translate-y-0.5 not-disabled:hover:bg-right not-disabled:hover:shadow-[0_18px_48px_-14px_rgba(217,70,239,0.8)] not-disabled:active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50';

/** The brand-gradient button look, shared by GlowButton and GlowLink. */
export function glowButtonClass(size: GlowSize = 'md', extra = ''): string {
  return `${BASE} ${BUTTON_SIZES[size]} ${extra}`.trim();
}

/**
 * The app's primary call to action: brand gradient, a StarBorder comet while it
 * is usable, and ClickSpark on press. One per view, for the action that matters.
 */
export function GlowButton({
  busy = false,
  size = 'md',
  block = false,
  disabled,
  type = 'button',
  className = '',
  children,
  ...rest
}: GlowButtonProps) {
  const inactive = disabled || busy;
  return (
    <ClickSpark className={block ? 'flex w-full' : 'inline-flex'}>
      <button
        {...rest}
        type={type}
        disabled={inactive}
        className={glowButtonClass(size, className)}
      >
        {!inactive && <StarBorder />}
        {busy && <Spinner decorative className="size-4" />}
        {children}
      </button>
    </ClickSpark>
  );
}
