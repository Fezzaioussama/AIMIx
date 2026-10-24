import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react';
import { useRef } from 'react';
import type { ReactNode } from 'react';

/**
 * A product "window" that starts tipped back in 3D and settles flat as it scrolls
 * into the middle of the screen. Under reduced motion it simply sits flat.
 */
export function PerspectiveWindow({ title, children }: { title: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start 95%', 'start 35%'] });
  const rotateX = useTransform(scrollYProgress, [0, 1], [22, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [0.94, 1]);

  return (
    <div ref={ref} className="[perspective:1400px]">
      <motion.div
        style={reduceMotion ? undefined : { rotateX, scale, transformOrigin: '50% 0%' }}
        className="mx-auto max-w-4xl overflow-hidden rounded-2xl border border-white/10 bg-slate-950/80 shadow-[0_40px_120px_-40px_rgba(99,102,241,0.55)] backdrop-blur-xl"
      >
        <div className="flex items-center gap-2 border-b border-white/[0.07] px-4 py-3">
          <span aria-hidden="true" className="size-2.5 rounded-full bg-white/15" />
          <span aria-hidden="true" className="size-2.5 rounded-full bg-white/15" />
          <span aria-hidden="true" className="size-2.5 rounded-full bg-white/15" />
          <span className="ml-3 text-xs font-medium text-slate-400">{title}</span>
        </div>
        {children}
      </motion.div>
    </div>
  );
}
