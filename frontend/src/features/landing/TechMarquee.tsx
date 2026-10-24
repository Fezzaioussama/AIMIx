import { TECH_STACK } from './content/site';

const COPIES = [0, 1] as const;

/**
 * The stack AIMIx runs on, drifting past in a loop. The loop is two identical copies
 * shifted by exactly one copy-width; the second is hidden from assistive tech. Under
 * reduced motion it stops and wraps into a static, centred row instead.
 */
export function TechMarquee() {
  return (
    <section aria-label="Built on" className="border-y border-white/[0.06] bg-white/[0.015] py-7">
      <p className="mb-5 text-center text-xs font-semibold tracking-[0.2em] text-slate-400 uppercase">
        Built on
      </p>
      <div className="overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
        <ul className="flex w-max gap-3 motion-safe:animate-marquee hover:[animation-play-state:paused] motion-reduce:w-full motion-reduce:flex-wrap motion-reduce:justify-center">
          {COPIES.flatMap((copy) =>
            TECH_STACK.map((name) => (
              <li
                key={`${copy}-${name}`}
                aria-hidden={copy === 1 ? true : undefined}
                className="flex items-center gap-5 px-3 font-mono text-xs font-semibold tracking-[0.18em] whitespace-nowrap text-slate-400 uppercase motion-reduce:[&[aria-hidden=true]]:hidden after:block after:size-1 after:rotate-45 after:bg-indigo-400/80"
              >
                {name}
              </li>
            )),
          )}
        </ul>
      </div>
    </section>
  );
}
