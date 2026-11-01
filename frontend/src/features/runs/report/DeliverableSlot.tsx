import {
  CircleDashed,
  CirclePause,
  Clock,
  Hand,
  PenLine,
  RotateCcw,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';

import type { Run } from '../../../core/api/types';
import { useNow } from '../../../core/hooks/useNow';
import { elapsedMs, formatDuration } from '../../../core/time';
import { FOCUS_RING } from '../../../core/ui/focus';
import { Heading } from '../../../core/ui/Heading';
import { ShinyText } from '../../../core/ui/reactbits/ShinyText';
import { SwapText } from '../../../core/ui/SwapText';
import { useJump } from './jump';
import { reportIds, type DeliverableState, type DeliverableView } from './reportModel';
import { slotWords } from './stepCopy';
import { TEXT_LINK } from './textStyles';

type SlotState = Exclude<DeliverableState, 'ready'>;

/** How a slot looks while its deliverable is on its way, or once it never will be. */
interface SlotLook {
  Icon: LucideIcon;
  icon: string;
  /** Still on its way: the skeleton bars show, and the words may shimmer. */
  live: boolean;
  /** Being written or revised: the words shimmer. */
  shine?: boolean;
}

const ON_ITS_WAY: SlotLook = { Icon: Clock, icon: 'text-slate-400', live: true };

/** Each slot state's look (Strategy + Registry, AGENTS.md §7). */
const SLOT_LOOK: Record<SlotState, SlotLook> = {
  queued: ON_ITS_WAY,
  waiting: ON_ITS_WAY,
  writing: { Icon: PenLine, icon: 'text-sky-300', live: true, shine: true },
  revising: { Icon: RotateCcw, icon: 'text-sky-300', live: true, shine: true },
  needsOk: { Icon: Hand, icon: 'text-amber-300', live: true },
  notFinished: { Icon: CirclePause, icon: 'text-slate-400', live: false },
  skipped: { Icon: CircleDashed, icon: 'text-slate-400', live: false },
};

/** A step that failed says so in amber; one stopped with its run stays quiet. */
const FAILED_LOOK: SlotLook = { Icon: TriangleAlert, icon: 'text-amber-300', live: false };

function lookOf(view: DeliverableView, state: SlotState): SlotLook {
  return state === 'notFinished' && view.step.status === 'failed' ? FAILED_LOOK : SLOT_LOOK[state];
}

/**
 * The state words. While the deliverable is on its way they sit in one ShinyText, so a
 * change of state swaps the words in place (M2); its band shows only through the
 * see-through colour of words being written, and stays hidden behind the others.
 */
function SlotWords({ words, look }: { words: string; look: SlotLook }) {
  if (!look.live) return <SwapText text={words} className="text-pretty text-slate-400" />;
  return (
    <ShinyText className={look.shine ? 'text-slate-300/80' : 'text-slate-300'}>
      <SwapText text={words} className="text-pretty" />
    </ShinyText>
  );
}

/** "Review the request": down to the approval this deliverable's agent waits on. */
function ReviewLink({ run, view }: { run: Run; view: DeliverableView }) {
  const jump = useJump();
  const approval = run.pending_approvals.find((item) => item.step_order === view.step.step_order);
  if (approval === undefined) return null;
  const target = `approval-${approval.id}`;
  return (
    <a
      href={`#${target}`}
      onClick={(event) => {
        event.preventDefault();
        jump(target);
      }}
      className={`mt-2 text-sm ${TEXT_LINK}`}
    >
      Review the request
    </a>
  );
}

/**
 * How long the agent has been writing, ticking beside "Being written" or "Being revised";
 * nothing for a step that waits (for your OK, or to start again after the check).
 */
function Elapsed({ view, look }: { view: DeliverableView; look: SlotLook }) {
  const running = look.shine === true && view.step.status === 'running';
  const now = useNow(running);
  const took = running ? elapsedMs(view.step.started_at, null, now) : null;
  if (took === null) return null;
  return <span className="shrink-0 text-slate-400 tabular-nums">· {formatDuration(took)}</span>;
}

/** Three still bars where the text will be: the shimmer of the words is the only motion. */
function Skeleton() {
  return (
    <div aria-hidden="true" className="mt-4 space-y-2">
      <div className="h-3 w-11/12 rounded bg-white/[0.06]" />
      <div className="h-3 w-full rounded bg-white/[0.06]" />
      <div className="h-3 w-2/3 rounded bg-white/[0.06]" />
    </div>
  );
}

interface DeliverableSlotProps {
  run: Run;
  view: DeliverableView;
  level: 2 | 3;
}

/**
 * A deliverable that is not a document yet, exactly where its document will land: its
 * title, who makes it, and what it is waiting for, or why it never came.
 */
export function DeliverableSlot({ run, view, level }: DeliverableSlotProps) {
  const ids = reportIds(run.id);
  const order = view.step.step_order;
  // DeliverableList shows a ready deliverable as its document, never as a slot.
  const state: SlotState = view.state === 'ready' ? 'notFinished' : view.state;
  const look = lookOf(view, state);
  return (
    <article
      id={ids.deliverable(order)}
      aria-labelledby={ids.title(order)}
      className="scroll-mt-[calc(var(--sticky-top,0px)+1rem)] rounded-2xl border border-dashed border-white/15 p-5"
    >
      <Heading
        level={level}
        id={ids.title(order)}
        tabIndex={-1}
        className={`rounded-sm text-lg font-semibold text-balance text-white ${FOCUS_RING}`}
      >
        {view.title}
      </Heading>
      {view.role && <p className="mt-1 text-sm text-slate-400">by {view.role}</p>}
      <p className="mt-3 flex items-start gap-2 text-sm">
        <look.Icon aria-hidden="true" className={`mt-0.5 size-4 shrink-0 ${look.icon}`} />
        <span className="flex min-w-0 flex-wrap gap-x-1.5">
          <SlotWords words={slotWords(view, run)} look={look} />
          <Elapsed view={view} look={look} />
        </span>
      </p>
      {state === 'needsOk' && <ReviewLink run={run} view={view} />}
      {look.live && <Skeleton />}
    </article>
  );
}
