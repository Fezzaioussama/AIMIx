import { motion, useReducedMotion, useScroll } from 'motion/react';
import { useRef } from 'react';

import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { PROCESS_STEPS } from './content/product';
import { LandingSection } from './LandingSection';
import { LiveDot } from './LiveDot';

const LAST = PROCESS_STEPS.length - 1;

/** Four numbered steps on a rail that fills with colour as the visitor scrolls down it. */
export function ProcessSection() {
  const rail = useRef<HTMLOListElement>(null);
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: rail, offset: ['start 65%', 'end 55%'] });

  return (
    <LandingSection
      id="how-it-works"
      eyebrow="How it works"
      title="From prototype to a repeatable run"
      description="Four steps take you from an empty workspace to a pipeline you can run again and again."
    >
      <ol ref={rail} className="relative mx-auto max-w-3xl">
        <span aria-hidden="true" className="absolute top-0 left-5 h-full w-px bg-white/10" />
        <motion.span
          aria-hidden="true"
          style={{ scaleY: reduceMotion ? 1 : scrollYProgress }}
          className="absolute top-0 left-5 h-full w-px origin-top bg-gradient-to-b from-sky-400 via-indigo-500 to-purple-500"
        />
        {PROCESS_STEPS.map((step, index) => (
          <li key={step.title} className="relative pb-10 pl-16 last:pb-0">
            <span
              aria-hidden="true"
              className="absolute top-0 left-0 grid size-10 place-items-center rounded-full border border-indigo-400/40 bg-slate-950 text-sm font-bold text-white shadow-[0_0_24px_-6px_rgba(99,102,241,0.8)]"
            >
              {index + 1}
            </span>
            <AnimatedContent whenInView direction="horizontal" distance={28}>
              <SpotlightCard className="p-6">
                <h3 className="text-xl font-bold text-white">{step.title}</h3>
                <p className="mt-2 text-slate-400">{step.detail}</p>
                <p className="mt-5 inline-flex items-center gap-2.5 rounded-lg bg-white/[0.04] px-3 py-1.5 font-mono text-xs text-slate-300">
                  <LiveDot tone={index === LAST ? 'emerald' : 'sky'} />
                  {step.status}
                </p>
              </SpotlightCard>
            </AnimatedContent>
          </li>
        ))}
      </ol>
    </LandingSection>
  );
}
