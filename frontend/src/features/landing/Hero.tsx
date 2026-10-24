import { ArrowRight } from 'lucide-react';

import { GlowLink } from '../../core/ui/GlowLink';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { BlurText } from '../../core/ui/reactbits/BlurText';
import { GradientText } from '../../core/ui/reactbits/GradientText';
import { ghostClass } from './GhostLink';
import { HeroScene } from './HeroScene';
import { HeroSteps } from './HeroSteps';
import { useLandingCtas } from './useLandingCtas';

function HeroActions() {
  const { primary } = useLandingCtas();
  return (
    <AnimatedContent delay={0.8} distance={14}>
      <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row lg:justify-start">
        <GlowLink to={primary.to} size="lg">
          {primary.label}
          <ArrowRight aria-hidden="true" className="size-5" />
        </GlowLink>
        <a href="#how-it-works" className={ghostClass('lg')}>
          See how it works
        </a>
      </div>
      <p className="mt-6 flex items-center justify-center gap-2 font-mono text-xs tracking-wide text-slate-500 lg:justify-start">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-emerald-400" />
        Bring your own model key
      </p>
    </AnimatedContent>
  );
}

function HeroCopy() {
  return (
    <div className="max-w-3xl text-center lg:text-left">
      <AnimatedContent delay={0.1} distance={10}>
        <p className="mb-7 flex items-center justify-center gap-3 font-mono text-[0.68rem] tracking-[0.24em] text-cyan-300 uppercase lg:justify-start">
          <span aria-hidden="true" className="h-px w-9 bg-cyan-300/70" />
          Visual agent runtime
        </p>
      </AnimatedContent>
      <h1
        id="hero-title"
        className="text-5xl leading-[0.98] font-extrabold tracking-[-0.045em] text-balance text-white sm:text-6xl lg:text-[4.6rem]"
      >
        <BlurText text="Design, coordinate, and run" className="justify-center lg:justify-start" />{' '}
        <span className="block pb-3">
          <GradientText>multi-agent workflows</GradientText>
        </span>
      </h1>
      <AnimatedContent delay={0.6} distance={14}>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-pretty text-slate-300 sm:text-xl lg:mx-0 lg:max-w-xl">
          AIMIx turns any hosted LLM into a team of agents. Give each one a role, a model, a prompt
          and a tool policy, chain them into stages, and watch the work flow downstream.
        </p>
      </AnimatedContent>
      <HeroActions />
    </div>
  );
}

/** Open with the promise, a 3D pipeline beside it, and the four steps underneath. */
export function Hero() {
  return (
    <section
      aria-labelledby="hero-title"
      className="relative isolate overflow-hidden px-4 pt-28 pb-24 sm:pt-36"
    >
      <HeroScene />
      <div className="relative z-10 mx-auto max-w-7xl lg:grid lg:min-h-[35rem] lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <HeroCopy />
      </div>
      <div className="relative z-10 mx-auto mt-14 max-w-6xl sm:mt-20">
        <AnimatedContent delay={1} distance={20}>
          <HeroSteps />
        </AnimatedContent>
      </div>
    </section>
  );
}
