/** Small secondary buttons of the Settings sections (the page's one GlowButton saves providers). */
const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60';

const TONES = {
  neutral: 'border-white/10 text-slate-200 hover:bg-white/10',
  accent: 'border-sky-400/50 bg-sky-400/15 text-sky-200 hover:bg-sky-400/25',
  danger: 'border-red-400/40 text-red-300 hover:bg-red-500/10',
} as const;

export type ActionTone = keyof typeof TONES;

export function actionButtonClass(tone: ActionTone = 'neutral'): string {
  return `${BASE} ${TONES[tone]}`;
}
