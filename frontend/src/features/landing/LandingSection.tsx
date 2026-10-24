import type { ReactNode } from 'react';

import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';

interface LandingSectionProps {
  /** Anchor target for the nav; the heading is `${id}-title`. */
  id: string;
  eyebrow: string;
  title: ReactNode;
  description?: string;
  children: ReactNode;
  className?: string;
}

/**
 * One landing section with an editorial heading rail rather than a repeated centred block.
 */
export function LandingSection({
  id,
  eyebrow,
  title,
  description,
  children,
  className = '',
}: LandingSectionProps) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="relative px-4 py-24 sm:py-32">
      <div className={`mx-auto max-w-6xl ${className}`}>
        <AnimatedContent
          whenInView
          className="grid gap-6 border-t border-white/10 pt-6 text-left lg:grid-cols-[0.32fr_1fr] lg:gap-12"
        >
          <p className="flex items-center gap-3 self-start font-mono text-xs font-semibold tracking-[0.2em] text-cyan-300 uppercase">
            <span aria-hidden="true" className="h-px w-8 bg-cyan-300/70" />
            {eyebrow}
          </p>
          <div>
            <h2
              id={`${id}-title`}
              className="max-w-4xl text-3xl font-extrabold tracking-[-0.035em] text-balance text-white sm:text-5xl"
            >
              {title}
            </h2>
            {description && (
              <p className="mt-5 max-w-2xl text-lg leading-relaxed text-pretty text-slate-400">
                {description}
              </p>
            )}
          </div>
        </AnimatedContent>
        <div className="mt-14 sm:mt-16">{children}</div>
      </div>
    </section>
  );
}
