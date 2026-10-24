import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { SECURITY_POINTS } from './content/solutions';
import { LandingSection } from './LandingSection';

export function SecuritySection() {
  return (
    <LandingSection
      id="security"
      eyebrow="Security"
      title="Your keys. Your pipelines. Your account."
      description="What you build in AIMIx stays private to you."
    >
      <ul className="grid gap-4 md:grid-cols-3">
        {SECURITY_POINTS.map((point, index) => (
          <li key={point.title}>
            <AnimatedContent whenInView delay={index * 0.1} className="h-full">
              <SpotlightCard className="h-full p-7">
                <span className="grid size-12 place-items-center rounded-xl bg-gradient-to-br from-sky-400/20 to-purple-500/25 text-sky-200 ring-1 ring-white/10">
                  <point.icon aria-hidden="true" className="size-6" />
                </span>
                <h3 className="mt-5 text-lg font-bold text-white">{point.title}</h3>
                <p className="mt-2 text-slate-400">{point.detail}</p>
              </SpotlightCard>
            </AnimatedContent>
          </li>
        ))}
      </ul>
    </LandingSection>
  );
}
