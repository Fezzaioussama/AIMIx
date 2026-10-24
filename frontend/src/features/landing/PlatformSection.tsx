import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { TiltCard } from '../../core/ui/TiltCard';
import { PLATFORM_FEATURES } from './content/product';
import { LandingSection } from './LandingSection';

// A three-column bento: rows of 2+1, 1+2, 2+1 so every row fills exactly.
const SPANS = ['lg:col-span-2', '', '', 'lg:col-span-2', 'lg:col-span-2', ''] as const;

/** A tiny chat exchange for the first card: the chat agent running a saved pipeline. */
function ChatSketch() {
  return (
    <div aria-hidden="true" className="mt-6 space-y-2 text-sm">
      <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-indigo-500/25 px-4 py-2 text-indigo-100">
        Run my launch-brief pipeline for fintech sales
      </p>
      <p className="flex w-fit items-center gap-2 rounded-2xl rounded-bl-md bg-white/[0.06] px-4 py-2 text-slate-300">
        Running 3 stages
        <span className="flex gap-1">
          {[0, 1, 2].map((dot) => (
            <span
              key={dot}
              style={{ animationDelay: `${dot * 0.15}s` }}
              className="size-1.5 rounded-full bg-sky-300 motion-safe:animate-wave"
            />
          ))}
        </span>
      </p>
    </div>
  );
}

export function PlatformSection() {
  return (
    <LandingSection
      id="platform"
      eyebrow="Platform"
      title="One workspace. Every agent. Your rules."
      description="Give every agent a job, a model and a set of tools, and keep the whole workflow in one place you can read, edit and run again."
    >
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORM_FEATURES.map((feature, index) => (
          <li key={feature.title} className={SPANS[index]}>
            <AnimatedContent whenInView delay={(index % 3) * 0.08} className="h-full">
              <TiltCard className="h-full">
                <SpotlightCard className="h-full p-6 sm:p-7">
                  <span className="grid size-11 place-items-center rounded-xl bg-gradient-to-br from-sky-400/20 via-indigo-500/20 to-purple-500/25 text-sky-200 ring-1 ring-white/10">
                    <feature.icon aria-hidden="true" className="size-5" />
                  </span>
                  <h3 className="mt-5 text-xl font-bold text-white">{feature.title}</h3>
                  <p className="mt-2 text-slate-400">{feature.detail}</p>
                  {index === 0 && <ChatSketch />}
                </SpotlightCard>
              </TiltCard>
            </AnimatedContent>
          </li>
        ))}
      </ul>
    </LandingSection>
  );
}
