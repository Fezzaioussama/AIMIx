import { Check } from 'lucide-react';

import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { TiltCard } from '../../core/ui/TiltCard';
import { USE_CASES } from './content/solutions';
import { LandingSection } from './LandingSection';

export function UseCasesSection() {
  return (
    <LandingSection
      id="use-cases"
      eyebrow="Use cases"
      title="Built for work that takes more than one prompt"
      description="Example workflows to start from. Each one is an ordinary pipeline you can open, edit and run."
    >
      <ul className="grid gap-4 lg:grid-cols-3">
        {USE_CASES.map((useCase, index) => (
          <li key={useCase.title}>
            <AnimatedContent whenInView delay={index * 0.1} className="h-full">
              <TiltCard className="h-full">
                <SpotlightCard className="h-full p-7" spotlightColor="rgba(168, 85, 247, 0.14)">
                  <useCase.icon aria-hidden="true" className="size-8 text-purple-300" />
                  <h3 className="mt-5 text-xl font-bold text-white">{useCase.title}</h3>
                  <ul className="mt-5 space-y-3">
                    {useCase.points.map((point) => (
                      <li key={point} className="flex gap-3 text-slate-300">
                        <Check aria-hidden="true" className="mt-1 size-4 shrink-0 text-sky-300" />
                        {point}
                      </li>
                    ))}
                  </ul>
                </SpotlightCard>
              </TiltCard>
            </AnimatedContent>
          </li>
        ))}
      </ul>
    </LandingSection>
  );
}
