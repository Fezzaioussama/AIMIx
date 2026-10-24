const BASE =
  'rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50';

/** The run controls' looks: quiet buttons beside a screen's one GlowButton. */
export const RUN_BUTTON = {
  stop: `${BASE} border-red-400/40 text-red-200 enabled:hover:bg-red-500/10`,
  resume: `${BASE} border-sky-400/50 bg-sky-500/10 text-sky-200 enabled:hover:bg-sky-500/20`,
  /** Also for links, so it hovers without `enabled:`. */
  neutral: `${BASE} border-white/15 text-slate-200 hover:bg-white/10`,
  danger: `${BASE} border-red-400/50 bg-red-500/15 text-red-100 enabled:hover:bg-red-500/25`,
} as const;
