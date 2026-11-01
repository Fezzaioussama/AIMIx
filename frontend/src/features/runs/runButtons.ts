import { FOCUS_RING, TOUCH } from '../../core/ui/focus';

/** Colour on hover, a slight press on click (§5 M10, M11). */
const BASE = `inline-flex items-center justify-center gap-1.5 ${TOUCH} rounded-lg border px-3 py-1.5 text-sm font-medium transition-[color,background-color,border-color,scale] duration-150 ease-out active:scale-[0.96] motion-reduce:transition-none motion-reduce:active:scale-100 ${FOCUS_RING} disabled:cursor-not-allowed disabled:opacity-50`;

/** The run controls' looks: quiet buttons beside a screen's one GlowButton. */
export const RUN_BUTTON = {
  stop: `${BASE} border-red-400/40 text-red-200 enabled:hover:bg-red-500/10`,
  resume: `${BASE} border-sky-400/50 bg-sky-500/10 text-sky-200 enabled:hover:bg-sky-500/20`,
  /** Also for links, so it hovers without `enabled:`. */
  neutral: `${BASE} border-white/15 text-slate-200 hover:bg-white/10`,
  danger: `${BASE} border-red-400/50 bg-red-500/15 text-red-100 enabled:hover:bg-red-500/25`,
} as const;
