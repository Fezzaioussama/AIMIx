import { describe, expect, it } from 'vitest';

import { makeRun, runStep } from '../testData';
import { flowRun, stepOf, teamRun } from './reportTestData';
import {
  fixingRound,
  isSentBack,
  isSettled,
  loopRounds,
  roundOf,
  sendsWorkBack,
} from './reviewRounds';

describe('sendsWorkBack', () => {
  it('is a REVISE with rounds left', () => {
    const reviewer = (rounds: number, verdict: 'pass' | 'revise' | null) => ({
      ...runStep(1, 'succeeded'),
      rounds,
      verdict,
    });
    expect(sendsWorkBack(reviewer(1, 'revise'), 2)).toBe(true);
    expect(sendsWorkBack(reviewer(2, 'revise'), 2)).toBe(true);
    expect(sendsWorkBack(reviewer(3, 'revise'), 2)).toBe(false);
    expect(sendsWorkBack(reviewer(1, 'pass'), 2)).toBe(false);
    expect(sendsWorkBack(reviewer(1, null), 2)).toBe(false);
    expect(sendsWorkBack({ ...reviewer(1, 'revise'), status: 'running' }, 2)).toBe(false);
  });
});

describe('loopRounds', () => {
  it('is in round 1 until the reviewer sends the work back, then in the next', () => {
    const first = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    expect(loopRounds(first)).toEqual([
      { reviewer: 4, first: 2, last: 3, maxRounds: 2, round: 1, total: 3 },
    ]);
    const back = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(loopRounds(back)[0].round).toBe(2);
  });

  it('is in the newest round any of its steps reached', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 3 }],
      ['succeeded', { rounds: 3 }],
      ['succeeded', { rounds: 2, verdict: 'revise' }],
    ]);
    expect(loopRounds(run)[0].round).toBe(3);
  });

  it('has none for a run without a reviewer', () => {
    expect(loopRounds(makeRun())).toEqual([]);
  });
});

describe('isSentBack and isSettled', () => {
  it('sends back the finished steps of the loop, the reviewer too, but not the steps before', () => {
    const run = flowRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
      ['pending'],
    ]);
    const loops = loopRounds(run);
    const sent = run.steps.map((step) => isSentBack(step, loops));
    const settled = run.steps.map((step) => isSettled(step, loops));
    expect(sent).toEqual([false, false, true, false]);
    expect(settled).toEqual([true, false, false, false]);
  });

  it('settles a step that finished the new round', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(isSettled(stepOf(run, 3), loopRounds(run))).toBe(true);
    expect(isSentBack(stepOf(run, 4), loopRounds(run))).toBe(true);
  });
});

describe('roundOf and fixingRound', () => {
  it('puts a sent-back step in its loop’s next round, out of 1 + max_rounds', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(roundOf(stepOf(run, 2), run)).toEqual({ round: 2, total: 3 });
    expect(fixingRound(run)).toEqual({ round: 2, total: 3 });
  });

  it('keeps a step in its own round, with no total outside any loop', () => {
    const run = teamRun([['succeeded'], ['running'], ['pending'], ['pending']]);
    expect(roundOf(stepOf(run, 1), run)).toEqual({ round: 1, total: null });
    expect(roundOf(stepOf(run, 2), run)).toEqual({ round: 1, total: 3 });
    expect(fixingRound(run)).toBeNull();
  });

  it('ends the fixing once the reviewer checks the new round', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['running', { rounds: 2 }],
    ]);
    expect(fixingRound(run)).toBeNull();
  });

  it('is not fixing once REVISE comes at the limit: the work is kept', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded', { rounds: 3 }],
      ['succeeded', { rounds: 3 }],
      ['succeeded', { rounds: 3, verdict: 'revise' }],
    ]);
    expect(fixingRound(run)).toBeNull();
    expect(roundOf(stepOf(run, 2), run)).toEqual({ round: 3, total: 3 });
  });
});
