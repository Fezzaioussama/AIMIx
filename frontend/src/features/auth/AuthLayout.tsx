import type { ReactNode } from 'react';

import { BRAND_COLORS } from '../../core/ui/brand';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { Aurora } from '../../core/ui/reactbits/Aurora';
import { RotatingText } from '../../core/ui/reactbits/RotatingText';

const TAGLINES = ['AI agents', 'model pipelines', 'smart workflows'] as const;

const FEATURES = [
  { title: 'Chat with any model', detail: 'Stream answers from your configured provider.' },
  {
    title: 'Build agent pipelines',
    detail: 'Chain and parallelise steps, each with its own tools.',
  },
  { title: 'Plan from a sentence', detail: 'Describe a workflow and let the planner draft it.' },
] as const;

/** The marketing half of the login and register screens; hidden on small screens. */
function AuthHero() {
  return (
    <div className="hidden max-w-lg flex-col lg:flex">
      <AnimatedContent distance={16}>
        <img src="/logo.png" alt="" className="mb-8 h-24 w-auto self-start" />
        <h1 className="text-5xl leading-tight font-extrabold tracking-tight text-white">
          Orchestrate{' '}
          <span className="block">
            <RotatingText texts={TAGLINES} colors={BRAND_COLORS} className="pb-1" />
          </span>
        </h1>
        <p className="mt-4 text-lg text-slate-400">
          One workspace to chat with LLMs and turn prompts into multi-agent pipelines.
        </p>
      </AnimatedContent>
      <ul className="mt-10 space-y-4">
        {FEATURES.map((feature, index) => (
          <li key={feature.title}>
            <AnimatedContent
              direction="horizontal"
              reverse
              distance={20}
              delay={0.3 + index * 0.12}
            >
              <div className="flex gap-3">
                <span className="mt-1.5 size-2 shrink-0 rounded-full bg-gradient-to-br from-sky-400 to-purple-500 shadow-[0_0_12px_rgba(129,140,248,0.8)]" />
                <span>
                  <span className="block font-semibold text-slate-100">{feature.title}</span>
                  <span className="text-sm text-slate-400">{feature.detail}</span>
                </span>
              </div>
            </AnimatedContent>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Full-screen aurora backdrop with the hero beside the auth card. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative isolate flex min-h-screen items-center justify-center overflow-hidden px-4 py-12">
      <Aurora className="inset-0 -z-10" layers={2} amplitude={1.1} blend={0.6} height={0.5} />
      {/* Fade the curtains into the page towards the bottom, keeping the top lit. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-gradient-to-b from-transparent via-[#050816]/40 to-[#050816]"
      />
      <div className="flex w-full max-w-6xl items-center justify-center gap-16 lg:justify-between">
        <AuthHero />
        {children}
      </div>
    </div>
  );
}
