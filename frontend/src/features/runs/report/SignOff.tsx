import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import type { Run } from '../../../core/api/types';
import { RenderedMarkdown } from '../../../core/markdown/RenderedMarkdown';
import {
  BLUR,
  DISTANCE,
  DURATION,
  EASE_SMOOTH_OUT,
  FADE,
  QUICK_EXIT,
} from '../../../core/ui/motionTokens';
import { ShinyText } from '../../../core/ui/reactbits/ShinyText';
import { DisclosureButton, Foldable } from '../../pipelines/FoldablePanel';
import { BottomHide } from './BottomHide';
import { CHECK_TONE } from './checkTone';
import { reportIds, type ReviewerView } from './reportModel';
import { signOff, type CheckToggle, type SignOffTone } from './signOffCopy';

/** The line's colour where it is not the usual slate (its icon comes from CHECK_TONE). */
const LINE_COLOUR: Partial<Record<SignOffTone, string>> = {
  concern: 'text-amber-300',
  checking: 'text-slate-300/80',
};

/**
 * M4, the second half of the hand-over: the line lands once the heading has swapped
 * (150ms later), rising 8px out of a 2px blur; it leaves with a quick fade.
 */
const LANDING = {
  initial: { opacity: 0, y: DISTANCE.base, filter: BLUR.small },
  animate: {
    opacity: 1,
    y: 0,
    filter: BLUR.none,
    transition: { duration: DURATION.slow, ease: EASE_SMOOTH_OUT, delay: DURATION.quick },
    transitionEnd: { filter: 'none' },
  },
  exit: { opacity: 0, transition: QUICK_EXIT },
} as const;

/** The element ids of a run's sign-off toggle and its full check. */
export function signOffIds(runId: number): { toggle: string; body: string } {
  const base = reportIds(runId).signOff;
  return { toggle: `${base}-toggle`, body: `${base}-body` };
}

interface FullCheckProps {
  runId: number;
  reviewer: ReviewerView;
  /** The level the check's own headings start at. */
  headingBase: number;
  toggle: CheckToggle;
  onClose: () => void;
}

/** The reviewer's whole answer beside a 1px gradient rule, signed with its role. */
function FullCheck({ runId, reviewer, headingBase, toggle, onClose }: FullCheckProps) {
  const { toggle: toggleId } = signOffIds(runId);
  const role = reviewer.definition.role.trim();
  const output = reviewer.step.output;
  return (
    <div className="relative pl-4">
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-px bg-gradient-to-b from-sky-400 via-indigo-500 to-purple-500"
      />
      <RenderedMarkdown markdown={output} headingBase={headingBase} className="text-slate-200" />
      {role && <p className="mt-3 text-sm text-slate-400">— {role}</p>}
      <BottomHide
        text={output}
        label={toggle.close}
        targetId={toggleId}
        toggleId={toggleId}
        onClose={onClose}
      />
    </div>
  );
}

interface CheckDisclosureProps {
  runId: number;
  reviewer: ReviewerView;
  level: 2 | 3;
  toggle: CheckToggle;
  open: boolean;
  onToggle: () => void;
}

/** "Read the full check", and the check it opens. */
function CheckDisclosure({ runId, reviewer, level, toggle, open, onToggle }: CheckDisclosureProps) {
  const ids = signOffIds(runId);
  return (
    <>
      {/* A flex row (no line strut), 4px down: the toggle's ring clears the line. */}
      <div className="mt-1 flex pl-6">
        <DisclosureButton
          open={open}
          controls={ids.body}
          label={open ? toggle.close : toggle.open}
          onToggle={onToggle}
          id={ids.toggle}
        />
      </div>
      <Foldable id={ids.body} open={open} size="small" bodyClassName="pt-3">
        <FullCheck
          runId={runId}
          reviewer={reviewer}
          headingBase={level + 1}
          toggle={toggle}
          onClose={onToggle}
        />
      </Foldable>
    </>
  );
}

interface SignOffProps {
  run: Run;
  reviewer: ReviewerView | null;
  /** The report's heading level: the check's own headings nest under it. */
  level: 2 | 3;
  open: boolean;
  onToggle: () => void;
}

/**
 * "Checked and approved by the Orchestrator.": what the step that checks the work said,
 * in one line under the outcome, with its full answer one click away. Nothing while the
 * check is still ahead, or when no step checks the work.
 */
export function SignOff({ run, reviewer, level, open, onToggle }: SignOffProps) {
  const reduced = useReducedMotion();
  const view = signOff(reviewer, run);
  const tone = view === null ? null : CHECK_TONE[view.tone];
  const colour = view === null ? '' : (LINE_COLOUR[view.tone] ?? 'text-slate-200');
  return (
    <AnimatePresence initial={false} mode="wait">
      {view !== null && tone !== null && reviewer !== null && (
        <motion.div
          key={view.key}
          id={reportIds(run.id).signOff}
          className="mt-4 scroll-mt-[calc(var(--sticky-top,0px)+1rem)]"
          {...(reduced ? FADE : LANDING)}
        >
          <p className="flex items-start gap-2 text-sm">
            <tone.Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${tone.icon}`} />
            {view.tone === 'checking' ? (
              <ShinyText className={colour}>{view.line}</ShinyText>
            ) : (
              <span className={`text-pretty ${colour}`}>{view.line}</span>
            )}
          </p>
          {view.toggle !== null && (
            <CheckDisclosure
              runId={run.id}
              reviewer={reviewer}
              level={level}
              toggle={view.toggle}
              open={open}
              onToggle={onToggle}
            />
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
