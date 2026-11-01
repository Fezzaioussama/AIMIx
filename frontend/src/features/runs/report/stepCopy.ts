/**
 * What a run's steps are doing, in plain words (brief §7): a deliverable's slot while it is
 * not a document yet, and an agent's row in "How your team got there". Pure.
 */
import type { Run, RunStatus, RunStep } from '../../../core/api/types';
import { elapsedMs, formatDuration } from '../../../core/time';
import { liveNodeStatus, type NodeStatus } from '../../pipelines/pipelineGraph';
import { joinWords } from '../../pipelines/revision';
import { roundLabel } from '../../pipelines/roundNotes';
import { describeCondition } from '../../pipelines/stepFlow';
import { isActive } from '../runStatus';
import { failureReason } from './outcomeCopy';
import {
  asksForOk,
  definitionOf,
  waitsFor,
  type DeliverableState,
  type DeliverableView,
} from './reportModel';
import { roundOf } from './reviewRounds';

/** The icon a timeline row shows: the diagram's status, or a request waiting for your OK. */
export type RowIcon = NodeStatus | 'needsOk';

export interface RowStatus {
  icon: RowIcon;
  words: string;
}

/** "round 2 of 3": the round a step is in, to follow other words. */
function roundWords(step: RunStep, run: Run): string {
  const { round, total } = roundOf(step, run);
  return roundLabel(round, total).toLowerCase();
}

/** "Starts when Research and Draft are done"; "Starting…" when nothing before it is left. */
function startsWhen(step: RunStep, run: Run): string {
  const first = waitsFor(step, run);
  if (first.length === 0) return 'Starting…';
  return `Starts when ${joinWords(first)} ${first.length === 1 ? 'is' : 'are'} done`;
}

/** " It runs only if the previous result contains “blog”."; nothing without a condition. */
function runsOnlyIf(step: RunStep, run: Run): string {
  const { steps, inputs } = run.definition;
  const described = describeCondition(definitionOf(run, step), steps, inputs);
  return described === null ? '' : ` It runs only if ${described}.`;
}

const RUN_STOPPED = 'Not finished: the run stopped before it was done.';

/** A step stopped while it ran, by why its run ended. */
const STOPPED_BY: Partial<Record<RunStatus, string>> = {
  cancelled: 'Not finished: you stopped the run before it was done.',
  interrupted: 'Not finished: the server restarted before it was done.',
};

function unfinished(step: RunStep, run: Run): string {
  if (step.status === 'pending') return 'Not finished: the run stopped before it started.';
  if (step.status === 'failed' && step.error !== null) {
    return `Not finished: it stopped because ${failureReason(step.error.code)}.`;
  }
  return (step.status === 'cancelled' ? STOPPED_BY[run.status] : undefined) ?? RUN_STOPPED;
}

type SlotRule = (step: RunStep, run: Run) => string;

/** A slot's words by the deliverable's state (Strategy + Registry, AGENTS.md §7). */
const SLOT_WORDS: Record<Exclude<DeliverableState, 'ready'>, SlotRule> = {
  queued: () => 'Not started yet',
  waiting: startsWhen,
  writing: () => 'Being written',
  revising: (step, run) => `Being revised · ${roundWords(step, run)}`,
  needsOk: () => 'Waiting for your OK',
  notFinished: unfinished,
  skipped: (step, run) => `Not made: its condition was not met.${runsOnlyIf(step, run)}`,
};

/** What a deliverable's slot says while it is not a document; empty once it is ready. */
export function slotWords(view: DeliverableView, run: Run): string {
  return view.state === 'ready' ? '' : SLOT_WORDS[view.state](view.step, run);
}

/** "Done · 4.0 s": the words, then how long the step took or has taken so far. */
function withTime(words: string, step: RunStep, now: number): string {
  const took = elapsedMs(step.started_at, step.finished_at, now);
  return took === null ? words : `${words} · ${formatDuration(took)}`;
}

type RowRule = (step: RunStep, run: Run, now: number) => string;

/** A row's words by the step's status as the diagram shows it (Strategy + Registry). */
const ROW_WORDS: Record<NodeStatus, RowRule> = {
  done: (step, _run, now) => withTime('Done', step, now),
  running: (step, run, now) =>
    withTime(step.rounds > 1 ? `Working on ${roundWords(step, run)}` : 'Working', step, now),
  waiting: (step, run) => (run.status === 'queued' ? 'Not started yet' : startsWhen(step, run)),
  pending: () => 'Did not run.',
  failed: (step) =>
    step.error === null
      ? 'Stopped before it finished.'
      : `Stopped because ${failureReason(step.error.code)}.`,
  stopped: () => 'Stopped before it finished.',
  skipped: (step, run) => `Skipped: its condition was not met.${runsOnlyIf(step, run)}`,
};

/**
 * An agent's row in the report's appendix: its icon and words. Pass `now` from `useNow` so
 * a running step's time keeps ticking.
 */
export function rowStatus(step: RunStep, run: Run, now: number = Date.now()): RowStatus {
  if (asksForOk(step, run)) return { icon: 'needsOk', words: 'Waiting for your OK' };
  const status = liveNodeStatus(step, isActive(run.status));
  return { icon: status, words: ROW_WORDS[status](step, run, now) };
}
