import { ArrowRight } from 'lucide-react';

import { GlowLink } from '../../core/ui/GlowLink';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { Aurora } from '../../core/ui/reactbits/Aurora';
import { GhostLink } from './GhostLink';
import { useLandingCtas } from './useLandingCtas';

/** The closing push, set on the same aurora the sign-in screens use. */
export function FinalCta() {
  const { primary, secondary } = useLandingCtas();

  return (
    <section aria-labelledby="cta-title" className="px-4 pb-24 sm:pb-32">
      <AnimatedContent whenInView scale={0.97}>
        <div className="relative isolate mx-auto max-w-5xl overflow-hidden rounded-3xl border border-white/10 px-6 py-20 text-center sm:py-24">
          <Aurora className="inset-0 -z-10" layers={2} amplitude={1.1} blend={0.6} height={0.6} />
          <div
            aria-hidden="true"
            className="absolute inset-0 -z-10 bg-gradient-to-b from-[#050816]/20 via-[#050816]/55 to-[#050816]/90"
          />
          <h2
            id="cta-title"
            className="mx-auto max-w-3xl text-3xl font-extrabold tracking-tight text-balance text-white sm:text-5xl"
          >
            Build your first <span className="whitespace-nowrap">multi-agent</span> pipeline today
          </h2>
          <p className="mx-auto mt-5 max-w-xl text-lg text-slate-300">
            Create an account, add a model key, and run a workflow where every agent knows its job.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <GlowLink to={primary.to} size="lg">
              {primary.label}
              <ArrowRight aria-hidden="true" className="size-5" />
            </GlowLink>
            <GhostLink to={secondary.to} size="lg">
              {secondary.label}
            </GhostLink>
          </div>
        </div>
      </AnimatedContent>
    </section>
  );
}
