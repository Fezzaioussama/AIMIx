import { useInView } from 'motion/react';
import { useRef } from 'react';

import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { CountUp } from '../../core/ui/reactbits/CountUp';
import { GradientText } from '../../core/ui/reactbits/GradientText';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { STATS } from './content/product';
import type { Stat } from './content/product';
import { LandingSection } from './LandingSection';

/** Counts up the first time it is on screen, not on page load. */
function StatCard({ stat, index }: { stat: Stat; index: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true });
  return (
    <AnimatedContent whenInView delay={index * 0.1} className="h-full">
      <SpotlightCard className="h-full p-7 text-center">
        <div ref={ref} className="text-6xl font-extrabold tracking-tight tabular-nums">
          <GradientText>
            <CountUp to={inView ? stat.value : 0} duration={1.4} />
          </GradientText>
        </div>
        <p className="mt-3 text-lg font-semibold text-white">{stat.label}</p>
        <p className="mt-1 text-sm text-slate-400">{stat.detail}</p>
      </SpotlightCard>
    </AnimatedContent>
  );
}

export function AboutSection() {
  return (
    <LandingSection
      id="about"
      eyebrow="What is AIMIx?"
      title="From a single prompt to a team of agents"
      description="Most LLM tools stop at one chat box. AIMIx adds the missing layer: define who does what, in which order and with which tools, then run it again whenever you need it."
    >
      <ul className="grid gap-4 sm:grid-cols-3">
        {STATS.map((stat, index) => (
          <li key={stat.label}>
            <StatCard stat={stat} index={index} />
          </li>
        ))}
      </ul>
    </LandingSection>
  );
}
