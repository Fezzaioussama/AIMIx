import { Link } from 'react-router-dom';
import type { LinkProps } from 'react-router-dom';

import { BUTTON_SIZES } from '../../core/ui/GlowButton';
import type { GlowSize } from '../../core/ui/GlowButton';

const BASE =
  'inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] font-semibold text-slate-100 backdrop-blur transition-colors hover:border-white/30 hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400';

/** The quieter button look, for the secondary action beside a GlowLink. */
export function ghostClass(size: GlowSize = 'md', extra = ''): string {
  return `${BASE} ${BUTTON_SIZES[size]} ${extra}`.trim();
}

interface GhostLinkProps extends LinkProps {
  size?: GlowSize;
}

export function GhostLink({ size = 'md', className = '', ...rest }: GhostLinkProps) {
  return <Link {...rest} className={ghostClass(size, className)} />;
}
