/**
 * What the reviewer (the step whose VERDICT: PASS/REVISE can send the work back) said about
 * the work, in plain words (brief §7): the report's one-line sign-off, and the check state
 * each deliverable's byline carries. Pure.
 */
import type { PipelineStep, Run, RunStepStatus } from '../../../core/api/types';
import { countOf } from '../../../core/usageFormat';
import { capitalised } from '../approvalFormat';
import { isActive } from '../runStatus';
import { failureReason } from './outcomeCopy';
import type { DeliverableView, ReviewerView } from './reportModel';
import { loopRounds, sendsWorkBack } from './reviewRounds';

/** How a check reads: its icon and colour. */
export type SignOffTone = 'checking' | 'fixes' | 'approved' | 'concern' | 'notChecked';

/** The words of the toggle that shows the reviewer's full answer. */
export interface CheckToggle {
  open: string;
  close: string;
}

export interface SignOffView {
  /** Changes whenever the line does: its tone and the reviewer's round. */
  key: string;
  tone: SignOffTone;
  line: string;
  /** Null while the reviewer has written nothing to read. */
  toggle: CheckToggle | null;
}

export interface BylineCheck {
  words: string;
  tone: SignOffTone;
}

const FULL_CHECK: CheckToggle = { open: 'Read the full check', close: 'Hide the full check' };
const FIXES_ASKED: CheckToggle = {
  open: 'Read what needs fixing',
  close: 'Hide what needs fixing',
};

/** "the Orchestrator", by the reviewer's role; "the reviewer" when it has none. */
export function reviewerName(definition: Pick<PipelineStep, 'role'>): string {
  const role = definition.role.trim();
  return role ? `the ${role}` : 'the reviewer';
}

/** "The Orchestrator", to start a sentence with. */
export function reviewerNameAtStart(definition: Pick<PipelineStep, 'role'>): string {
  return capitalised(reviewerName(definition));
}

function maxRounds(reviewer: ReviewerView): number {
  return reviewer.definition.review?.max_rounds ?? 0;
}

/** What the reviewer's state says: its tone and line, and whether it asked for fixes. */
interface Check {
  tone: SignOffTone;
  line: string;
  fixes?: boolean;
}

function stoppedFirst(name: string): Check {
  return {
    tone: 'notChecked',
    line: `Not checked: the run stopped before ${name} could check the work.`,
  };
}

/** The lines of a reviewer's final answer, by its verdict ('none': it gave none). */
const VERDICT_LINES: Record<'pass' | 'revise' | 'none', (name: string, fixed: number) => Check> = {
  pass: (name, fixed) => ({
    tone: 'approved',
    line:
      fixed === 0
        ? `Checked and approved by ${name}.`
        : `Approved by ${name} after ${countOf(fixed, 'round')} of fixes.`,
  }),
  revise: (name, fixed) => ({
    tone: 'concern',
    line: `${capitalised(name)} still asked for fixes after ${countOf(fixed, 'round')}, so the last version was kept. Read the check before you use it.`,
  }),
  none: (name) => ({
    tone: 'concern',
    line: `${capitalised(name)} gave no clear verdict, so the work was kept as it is.`,
  }),
};

function answered(reviewer: ReviewerView, run: Run, name: string): Check {
  if (sendsWorkBack(reviewer.step, maxRounds(reviewer))) {
    const check = isActive(run.status)
      ? { tone: 'fixes' as const, line: `${capitalised(name)} asked for fixes.` }
      : stoppedFirst(name);
    return { ...check, fixes: true };
  }
  return VERDICT_LINES[reviewer.step.verdict ?? 'none'](name, reviewer.step.rounds - 1);
}

type CheckRule = (reviewer: ReviewerView, run: Run, name: string) => Check | null;

/** The sign-off by the reviewer step's status (Strategy + Registry, AGENTS.md §7). */
const CHECK_BY_STATUS: Record<RunStepStatus, CheckRule> = {
  // Nothing to say yet while the run is still on its way to the check.
  pending: (_reviewer, run, name) => (isActive(run.status) ? null : stoppedFirst(name)),
  running: (reviewer, _run, name) => ({
    tone: 'checking',
    line: `${capitalised(name)} is checking the ${reviewer.step.rounds > 1 ? 'revised ' : ''}work…`,
  }),
  succeeded: answered,
  failed: (reviewer, run, name) => ({
    tone: 'notChecked',
    line: `Not checked: ${name} stopped because ${failureReason(reviewer.step.error?.code ?? run.error?.code)}.`,
  }),
  cancelled: (_reviewer, _run, name) => stoppedFirst(name),
  skipped: () => ({
    tone: 'notChecked',
    line: 'Not checked: the check was skipped because its condition was not met.',
  }),
};

/** The report's one-line sign-off; null without a reviewer, or while the check is still ahead. */
export function signOff(reviewer: ReviewerView | null, run: Run): SignOffView | null {
  if (reviewer === null) return null;
  const check = CHECK_BY_STATUS[reviewer.step.status](
    reviewer,
    run,
    reviewerName(reviewer.definition),
  );
  if (check === null) return null;
  const readable = reviewer.step.output.trim() !== '';
  return {
    key: `${check.tone}-${reviewer.step.rounds}`,
    tone: check.tone,
    line: check.line,
    toggle: readable ? (check.fixes ? FIXES_ASKED : FULL_CHECK) : null,
  };
}

const STOPPED_CHECK: BylineCheck = { words: 'Not checked: the run stopped', tone: 'notChecked' };

/** What a byline's check part is made from. */
interface BylineFacts {
  name: string;
  reviewer: ReviewerView;
  view: DeliverableView;
  run: Run;
}

/** A final answer's byline words, by its verdict. */
const VERDICT_BYLINES: Record<
  'pass' | 'revise' | 'none',
  (name: string, fixed: number) => BylineCheck
> = {
  pass: (name, fixed) => ({
    words: fixed === 0 ? `Approved by ${name}` : `Approved by ${name} after fixes`,
    tone: 'approved',
  }),
  revise: (name) => ({ words: `${capitalised(name)} still asked for fixes`, tone: 'concern' }),
  none: (name) => ({ words: `No clear verdict from ${name}`, tone: 'concern' }),
};

function answeredByline({ name, reviewer, view, run }: BylineFacts): BylineCheck {
  const active = isActive(run.status);
  // A later round than the reviewer's last answer: revised, and not checked again yet.
  if (view.step.rounds > reviewer.step.rounds) {
    return active
      ? { words: `Revised, waiting for ${name}’s check`, tone: 'fixes' }
      : STOPPED_CHECK;
  }
  if (sendsWorkBack(reviewer.step, maxRounds(reviewer))) {
    return active
      ? { words: `${capitalised(name)} asked for fixes`, tone: 'fixes' }
      : STOPPED_CHECK;
  }
  return VERDICT_BYLINES[reviewer.step.verdict ?? 'none'](name, reviewer.step.rounds - 1);
}

/** The byline's check part by the reviewer step's status (Strategy + Registry). */
const BYLINE_BY_STATUS: Record<RunStepStatus, (facts: BylineFacts) => BylineCheck> = {
  pending: ({ run }) =>
    isActive(run.status) ? { words: 'Not checked yet', tone: 'notChecked' } : STOPPED_CHECK,
  running: ({ name }) => ({ words: `Being checked by ${name}`, tone: 'checking' }),
  succeeded: answeredByline,
  failed: () => STOPPED_CHECK,
  cancelled: () => STOPPED_CHECK,
  skipped: () => ({ words: 'Not checked: the check was skipped', tone: 'notChecked' }),
};

/**
 * Whether the reviewer reads the deliverable: the server hands it the stage just before its
 * own and its loop's earlier deliverables (StepNode._work, loops._loop), never a stage
 * before its loop, its own stage or a later one.
 */
function readsIt(reviewer: ReviewerView, view: DeliverableView, run: Run): boolean {
  const loop = loopRounds(run).find((item) => item.reviewer === reviewer.step.step_order);
  const stage = view.step.stage;
  return loop !== undefined && stage >= loop.first && stage < reviewer.step.stage;
}

/**
 * The check state a ready deliverable's byline carries; null for a slot, without a reviewer,
 * and for a deliverable the reviewer does not read.
 */
export function bylineCheck(
  reviewer: ReviewerView | null,
  view: DeliverableView,
  run: Run,
): BylineCheck | null {
  if (reviewer === null || view.state !== 'ready' || !readsIt(reviewer, view, run)) return null;
  const name = reviewerName(reviewer.definition);
  return BYLINE_BY_STATUS[reviewer.step.status]({ name, reviewer, view, run });
}
