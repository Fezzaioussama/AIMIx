import { Link } from 'react-router-dom';
import type { LinkProps } from 'react-router-dom';

import { glowButtonClass } from './GlowButton';
import type { GlowSize } from './GlowButton';
import { ClickSpark } from './reactbits/ClickSpark';
import { StarBorder } from './reactbits/StarBorder';

interface GlowLinkProps extends LinkProps {
  size?: GlowSize;
}

/**
 * GlowButton's look for navigation: a real link (middle-click, open in a new tab)
 * with the brand gradient, StarBorder comet and ClickSpark. One per view, like GlowButton.
 */
export function GlowLink({ size = 'md', className = '', children, ...rest }: GlowLinkProps) {
  return (
    <ClickSpark className="inline-flex">
      <Link {...rest} className={glowButtonClass(size, className)}>
        <StarBorder />
        {children}
      </Link>
    </ClickSpark>
  );
}
