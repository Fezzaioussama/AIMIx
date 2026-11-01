import {
  BadgeCheck,
  CircleDashed,
  LoaderCircle,
  RotateCcw,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';

import type { SignOffTone } from './signOffCopy';

/** How a check state looks beside its words: an icon, and the colour that tells its tone. */
export interface ToneLook {
  Icon: LucideIcon;
  /** The icon's classes: its colour, and the spin of a check under way. */
  icon: string;
  /** The colour of the words when they carry the tone, as a byline's check part does. */
  text: string;
}

/**
 * Each check state's look (brief §4 SignOff), shared by the sign-off line and every
 * deliverable's byline. Colour never stands alone: the words always say the state.
 */
export const CHECK_TONE: Record<SignOffTone, ToneLook> = {
  approved: { Icon: BadgeCheck, icon: 'text-emerald-300', text: 'text-emerald-300' },
  concern: { Icon: TriangleAlert, icon: 'text-amber-300', text: 'text-amber-300' },
  checking: {
    Icon: LoaderCircle,
    icon: 'text-sky-300 motion-safe:animate-spin',
    text: 'text-sky-300',
  },
  fixes: { Icon: RotateCcw, icon: 'text-sky-300', text: 'text-sky-300' },
  notChecked: { Icon: CircleDashed, icon: 'text-slate-400', text: 'text-slate-400' },
};
