import { describe, expect, it } from 'vitest';

import { groupByStage, nextStage } from './stages';

describe('groupByStage', () => {
  it('orders stages ascending and keeps item order inside a stage', () => {
    const steps = [
      { id: 'c', stage: 2 },
      { id: 'a', stage: 1 },
      { id: 'b', stage: 1 },
    ];
    const groups = groupByStage(steps, (step) => step.stage);
    expect(groups.map((group) => group.stage)).toEqual([1, 2]);
    expect(groups[0].items.map((step) => step.id)).toEqual(['a', 'b']);
  });
});

describe('nextStage', () => {
  it('places a new step after the last stage', () => {
    expect(nextStage([{ stage: 1 }, { stage: 1 }, { stage: 3 }])).toBe(4);
    expect(nextStage([])).toBe(1);
  });
});
