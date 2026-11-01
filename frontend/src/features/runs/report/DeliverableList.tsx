import { AnimatePresence, motion, useReducedMotion } from 'motion/react';

import type { Run } from '../../../core/api/types';
import { AiNotice } from '../../../core/ui/AiNotice';
import { BLUR, DISTANCE, DURATION, EASE_SMOOTH_OUT } from '../../../core/ui/motionTokens';
import { DeliverableDoc } from './DeliverableDoc';
import { DeliverableSlot } from './DeliverableSlot';
import type { DeliverableView, ReportModel } from './reportModel';
import { bylineCheck } from './signOffCopy';

/** Longer than this, a document arriving skips the blur: blurring a long page is costly. */
const BLUR_MAX_CHARS = 1500;

const QUICK_EXIT = { duration: DURATION.quick, ease: 'easeInOut' } as const;

/**
 * M5, the hand-over: the document rises 8px into place over 400ms (out of a 2px blur when
 * it is short) while its slot blurs away in 150ms. Sent back, the document fades out and
 * the slot fades in.
 */
function documentArrives(blur: boolean) {
  return {
    initial: { opacity: 0, y: DISTANCE.base, ...(blur && { filter: BLUR.small }) },
    animate: {
      opacity: 1,
      y: 0,
      ...(blur && { filter: BLUR.none }),
      transition: { duration: DURATION.slow, ease: EASE_SMOOTH_OUT },
      // No filter left behind: it would cost every repaint of the page under it.
      transitionEnd: { filter: 'none' },
    },
    exit: { opacity: 0, transition: QUICK_EXIT },
  };
}

const SLOT_MOTION = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: DURATION.fast, ease: EASE_SMOOTH_OUT } },
  exit: { opacity: 0, filter: BLUR.small, transition: QUICK_EXIT },
};

/** Reduced motion: a 150ms fade each way, nothing moves or blurs. */
const FADING = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: DURATION.quick } },
  exit: { opacity: 0, transition: { duration: DURATION.quick } },
};

interface DeliverableListProps {
  run: Run;
  model: ReportModel;
  level: 2 | 3;
}

/** One deliverable's place: its document once ready, its slot until then (`popLayout`). */
function Deliverable({
  run,
  model,
  level,
  view,
}: DeliverableListProps & { view: DeliverableView }) {
  const reduced = useReducedMotion();
  const ready = view.state === 'ready';
  const short = view.step.output.length <= BLUR_MAX_CHARS;
  const look = reduced ? FADING : ready ? documentArrives(short) : SLOT_MOTION;
  return (
    <div className="relative">
      <AnimatePresence initial={false} mode="popLayout">
        <motion.div key={ready ? `doc-${view.step.rounds}` : 'slot'} {...look}>
          {ready ? (
            <DeliverableDoc
              run={run}
              view={view}
              check={bylineCheck(model.reviewer, view, run)}
              level={level}
            />
          ) : (
            <DeliverableSlot run={run} view={view} level={level} />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/**
 * The answer: what the team made, in run order, each where it will stay. The AI notice
 * leads in once, as soon as any agent has written something.
 */
export function DeliverableList({ run, model, level }: DeliverableListProps) {
  if (model.deliverables.length === 0) return null;
  const written = run.steps.some((step) => step.status === 'succeeded' && step.output.trim());
  return (
    <section aria-label="Deliverables">
      {written && <AiNotice />}
      <div className="mt-4 space-y-14">
        {model.deliverables.map((view) => (
          <Deliverable
            key={view.step.step_order}
            run={run}
            model={model}
            level={level}
            view={view}
          />
        ))}
      </div>
    </section>
  );
}
