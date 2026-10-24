/**
 * Button looks for in-card actions that sit beside a page's GlowButton (one per view):
 * a solid primary and an outlined secondary. White on indigo-600 keeps 6:1 contrast,
 * so hover adds a glow rather than a lighter fill.
 */
export const PRIMARY_BUTTON =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-shadow hover:shadow-[0_8px_24px_-10px_rgba(129,140,248,0.9)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none';

export const SECONDARY_BUTTON =
  'inline-flex items-center justify-center gap-2 rounded-lg border border-white/15 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50';
