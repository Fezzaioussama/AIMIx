import type { RunStep } from '../../core/api/types';
import { timesWords } from './stepFlow';

/** "Round 2 of 3": which time a step ran in a review loop, out of the most it may run. */
export function roundLabel(round: number, total: number | null): string {
  return total === null ? `Round ${round}` : `Round ${round} of ${total}`;
}

/**
 * What a reviewer's last answer led to, in words (null when there is nothing to add).
 * `maxRounds` is how many times its loop may send the work back; `step.rounds - 1` times
 * it already did before this answer.
 */
export function reviewNote(
  step: Pick<RunStep, 'rounds' | 'verdict'>,
  maxRounds: number,
): string | null {
  const before = step.rounds - 1;
  const earlier = before > 0 ? `Sent back ${timesWords(before)}, then ` : '';
  if (step.verdict === 'revise') {
    return before >= maxRounds
      ? `${earlier}accepted`
      : `Asked for fixes: the work goes back for round ${step.rounds + 1}`;
  }
  if (step.verdict === 'pass') return before > 0 ? `${earlier}approved` : null;
  return before > 0
    ? `${earlier}moved on without a verdict`
    : 'It gave no verdict, so the work moved on';
}
