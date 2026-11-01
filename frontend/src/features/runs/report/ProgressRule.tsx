import type { OutcomeKind } from './reportModel';

/** How the rule reads: filling while the team works, whole at the hand-over, or cut short. */
type RuleLook = 'working' | 'complete' | 'short';

const LOOK_BY_OUTCOME: Record<OutcomeKind, RuleLook> = {
  queued: 'working',
  running: 'working',
  checking: 'working',
  fixing: 'working',
  waiting: 'working',
  done: 'complete',
  doneNothing: 'complete',
  limit: 'short',
  failed: 'short',
  stopped: 'short',
  interrupted: 'short',
};

/**
 * The brand gradient's opacity (§5 M3): softened while the team works, full at the end;
 * a run cut short fades it out over 250ms, leaving the slate fill beneath.
 */
const GRADIENT: Record<RuleLook, string> = {
  working: 'opacity-70 duration-400',
  complete: 'opacity-100 duration-400',
  short: 'opacity-0 duration-250',
};

const FILL =
  'absolute inset-0 origin-left transition-[transform,opacity] ease-smooth-out motion-reduce:transition-none';

interface ProgressRuleProps {
  outcome: OutcomeKind;
  /** Agents done with, out of `total`. */
  done: number;
  total: number;
}

/**
 * The 2px rule that closes the outcome header: it fills as agents finish and completes at
 * the hand-over. Decorative: the sentence above already says how far the team is.
 */
export function ProgressRule({ outcome, done, total }: ProgressRuleProps) {
  const look = LOOK_BY_OUTCOME[outcome];
  const share = look === 'complete' ? 1 : total > 0 ? done / total : 0;
  const width = { transform: `scaleX(${share})` };
  return (
    <div
      aria-hidden="true"
      data-look={look}
      className="relative mt-6 h-0.5 overflow-hidden rounded-full bg-white/[0.08]"
    >
      <div
        style={width}
        className={`${FILL} bg-slate-500/60 duration-400 ${look === 'short' ? 'opacity-100' : 'opacity-0'}`}
      />
      <div
        style={width}
        className={`${FILL} bg-gradient-to-r from-sky-400 via-indigo-500 to-purple-500 ${GRADIENT[look]}`}
      />
    </div>
  );
}
