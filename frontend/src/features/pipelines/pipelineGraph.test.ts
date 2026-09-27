import { describe, expect, it } from 'vitest';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { buildGraph } from './pipelineGraph';

const steps: PipelineStep[] = [
  { order: 1, stage: 1, prompt: 'a', model: 'v/m' },
  { order: 2, stage: 1, prompt: 'b', model: 'v/m' },
  { order: 3, stage: 2, prompt: 'c', model: 'v/m' },
];

describe('buildGraph', () => {
  it('groups steps by stage and marks unrun steps pending', () => {
    const graph = buildGraph(steps, [], false);
    expect(graph.map((stage) => stage.items.map((node) => node.order))).toEqual([[1, 2], [3]]);
    expect(graph[0].items[0].status).toBe('pending');
  });

  it('marks every step running while a run is in flight', () => {
    const graph = buildGraph(steps, [], true);
    expect(graph.flatMap((stage) => stage.items).every((node) => node.status === 'running')).toBe(
      true,
    );
  });

  it('marks steps with a result done and reports the output length', () => {
    const results: StepResult[] = [
      { step_order: 1, stage: 1, model: 'v/m', input_used: 'x', output: 'hello' },
    ];
    const [first] = buildGraph(steps, results, false);
    expect(first.items[0]).toMatchObject({ status: 'done', outputLength: 5 });
    expect(first.items[1]).toMatchObject({ status: 'pending', outputLength: null });
  });
});
