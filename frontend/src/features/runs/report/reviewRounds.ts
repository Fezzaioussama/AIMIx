/**
 * Where a run's review loops stand (pure): the round each loop is in, and which finished
 * steps a reviewer's REVISE sent back to be done again. The server clears a step's row only
 * when its stage starts again (`_restarted` in backend/api/services/run_recorder.py), so
 * until then a sent-back step still reads as finished, in an earlier round.
 */
import type { Run, RunStep, RunStepStatus } from '../../../core/api/types';
import { reviewLoops } from '../../pipelines/stepFlow';

/** A review round, and the most rounds its loop may run (null outside a loop). */
export interface RoundView {
  round: number;
  total: number | null;
}

/** A review loop (stage numbers), the round it is in, and the most rounds it may run. */
export interface LoopRound {
  reviewer: number;
  first: number;
  last: number;
  round: number;
  total: number;
}

/** Whether a reviewer's answer sends the work back: REVISE, with rounds left in its loop. */
export function sendsWorkBack(step: RunStep, maxRounds: number): boolean {
  return step.status === 'succeeded' && step.verdict === 'revise' && step.rounds - 1 < maxRounds;
}

/**
 * The round each review loop the engine follows is in. A step's row holds the newest round
 * it reached, so the loop is in the newest round any of its steps reached (as
 * `initial_loops` in backend/api/services/multiagent/loops.py reads it); once its reviewer
 * sent the work back, in the next one, even before a step has started it again.
 */
export function loopRounds(run: Run): LoopRound[] {
  return reviewLoops(run.definition.steps).map((loop) => {
    const members = run.steps.filter((step) => step.stage >= loop.first && step.stage <= loop.last);
    const latest = Math.max(1, ...members.map((step) => step.rounds));
    const reviewer = run.steps.find((step) => step.step_order === loop.reviewer);
    const back =
      reviewer !== undefined &&
      reviewer.rounds === latest &&
      sendsWorkBack(reviewer, loop.maxRounds);
    return { ...loop, round: back ? latest + 1 : latest, total: loop.maxRounds + 1 };
  });
}

function loopOf(step: RunStep, loops: LoopRound[]): LoopRound | undefined {
  return loops.find((loop) => step.stage >= loop.first && step.stage <= loop.last);
}

const FINAL: ReadonlySet<RunStepStatus> = new Set<RunStepStatus>(['succeeded', 'skipped']);

/** Finished in a round its loop has gone past: the review sent it back to be done again. */
export function isSentBack(step: RunStep, loops: LoopRound[]): boolean {
  const loop = loopOf(step, loops);
  return FINAL.has(step.status) && loop !== undefined && step.rounds < loop.round;
}

/** Done with for good: finished or skipped, and not sent back. */
export function isSettled(step: RunStep, loops: LoopRound[]): boolean {
  return FINAL.has(step.status) && !isSentBack(step, loops);
}

/** The round a step is in (a sent-back step: its loop's next one), and its loop's most. */
export function roundOf(step: RunStep, run: Run): RoundView {
  const loops = loopRounds(run);
  const loop = loopOf(step, loops);
  const round = loop !== undefined && isSentBack(step, loops) ? loop.round : step.rounds;
  return { round, total: loop?.total ?? null };
}

/** The round the work is being fixed in, while a loop runs one its reviewer has not checked. */
export function fixingRound(run: Run): RoundView | null {
  const loop = loopRounds(run).find((item) => {
    const reviewer = run.steps.find((step) => step.step_order === item.reviewer);
    return (reviewer?.rounds ?? 1) < item.round;
  });
  return loop === undefined ? null : { round: loop.round, total: loop.total };
}
