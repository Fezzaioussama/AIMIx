import type { ButtonHTMLAttributes } from 'react';

import { ClickSpark } from './reactbits/ClickSpark';
import { StarBorder } from './reactbits/StarBorder';
import { Spinner } from './Spinner';

interface GlowButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Shows a spinner and blocks clicks; the caller's label should say what is happening. */
  busy?: boolean;
  size?: 'md' | 'lg';
  /** Stretch to the container's width. */
  block?: boolean;
}

const SIZES = { md: 'px-6 py-3 text-sm', lg: 'px-8 py-4 text-base' };

const BASE =
  'relative isolate inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 via-indigo-500 to-purple-500 bg-[length:200%_100%] bg-left font-semibold text-white shadow-[0_10px_30px_-12px_rgba(99,102,241,0.8)] transition-[background-position,transform,box-shadow] duration-500 enabled:hover:-translate-y-0.5 enabled:hover:bg-right enabled:hover:shadow-[0_16px_40px_-12px_rgba(168,85,247,0.85)] enabled:active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50';

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
        className={`${BASE} ${SIZES[size]} ${className}`}
      >
        {!inactive && <StarBorder />}
        {busy && <Spinner decorative className="size-4" />}
        {children}
      </button>
    </ClickSpark>
  );
}
