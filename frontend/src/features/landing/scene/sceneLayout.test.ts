import { describe, expect, it } from 'vitest';

import { buildPipelineLayout, buildStars, stageProgress } from './sceneLayout';

describe('buildPipelineLayout', () => {
  const layout = buildPipelineLayout();

  it('fans out from one input and converges on one deliverable', () => {
    const perStage = Array.from(
      { length: layout.stageCount },
      (_, stage) => layout.nodes.filter((node) => node.stage === stage).length,
    );
    expect(perStage[0]).toBe(1);
    expect(perStage[perStage.length - 1]).toBe(1);
    expect(Math.max(...perStage)).toBeGreaterThan(1);
  });

  it('only connects each stage to the one right after it', () => {
    expect(layout.edges.length).toBeGreaterThan(0);
    for (const { from, to } of layout.edges) {
      expect(layout.nodes[to].stage).toBe(layout.nodes[from].stage + 1);
    }
  });

  it('lays stages out left to right', () => {
    const xs = layout.nodes.map((node) => node.position[0]);
    for (let index = 1; index < layout.nodes.length; index += 1) {
      const previous = layout.nodes[index - 1];
      const current = layout.nodes[index];
      if (current.stage > previous.stage) expect(xs[index]).toBeGreaterThan(xs[index - 1]);
    }
  });

  it('is identical on every call, so renders never differ', () => {
    expect(buildPipelineLayout()).toEqual(layout);
    expect(buildStars(40)).toEqual(buildStars(40));
  });
});

describe('stageProgress', () => {
  it('runs from 0 at the input to 1 at the deliverable', () => {
    expect(stageProgress(0, 5)).toBe(0);
    expect(stageProgress(2, 5)).toBe(0.5);
    expect(stageProgress(4, 5)).toBe(1);
  });

  it('does not divide by zero for a single stage', () => {
    expect(stageProgress(0, 1)).toBe(0);
  });
});

describe('buildStars', () => {
  it('returns one xyz triple per star, all behind the constellation', () => {
    const stars = buildStars(25);
    expect(stars).toHaveLength(75);
    for (let index = 2; index < stars.length; index += 3) expect(stars[index]).toBeLessThan(0);
  });
});
