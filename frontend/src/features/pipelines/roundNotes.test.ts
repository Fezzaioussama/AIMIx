import { describe, expect, it } from 'vitest';

import { reviewNote, roundLabel } from './roundNotes';

describe('roundLabel', () => {
  it('says which time a step ran, out of the most it may', () => {
    expect(roundLabel(2, 3)).toBe('Round 2 of 3');
    expect(roundLabel(3, 3)).toBe('Round 3 of 3');
  });

  it('says only the round when the loop is not known', () => {
    expect(roundLabel(2, null)).toBe('Round 2');
  });
});

describe('reviewNote', () => {
  const note = (rounds: number, verdict: 'pass' | 'revise' | null, maxRounds = 2) =>
    reviewNote({ rounds, verdict }, maxRounds);

  it('has nothing to add to a reviewer that approved the first time', () => {
    expect(note(1, 'pass')).toBeNull();
  });

  it('says how often the work went back before it was approved', () => {
    expect(note(2, 'pass')).toBe('Sent back 1 time, then approved');
    expect(note(3, 'pass')).toBe('Sent back 2 times, then approved');
  });

  it('says the work was accepted once the rounds ran out on a request for fixes', () => {
    expect(note(3, 'revise', 2)).toBe('Sent back 2 times, then accepted');
    expect(note(2, 'revise', 1)).toBe('Sent back 1 time, then accepted');
    expect(note(6, 'revise', 5)).toBe('Sent back 5 times, then accepted');
  });

  it('says the work goes back again while rounds are left', () => {
    expect(note(1, 'revise', 2)).toBe('Asked for fixes: the work goes back for round 2');
    expect(note(2, 'revise', 3)).toBe('Asked for fixes: the work goes back for round 3');
  });

  it('says so when the reviewer gave no verdict', () => {
    expect(note(1, null)).toBe('It gave no verdict, so the work moved on');
    expect(note(2, null)).toBe('Sent back 1 time, then moved on without a verdict');
  });
});
