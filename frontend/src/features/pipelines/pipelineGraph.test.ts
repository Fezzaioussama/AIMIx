import { describe, expect, it } from 'vitest';

import type { PipelineStep, StepResult } from '../../core/api/types';
import { buildGraph } from './pipelineGraph';

function step(order: number, stage: number, isOutput = false): PipelineStep {
  return { order, stage, title: '', is_output: isOutput, prompt: 'p', model: 'v/m' };
}

function result(order: number, stage: number, isOutput: boolean): StepResult {
  return {
    step_order: order,
    stage,
    title: '',
    model: 'v/m',
    input_used: 'x',
    output: 'hello',
    is_output: isOutput,
  };
}

const steps = [step(1, 1), step(2, 1), step(3, 2)];
const nodesOf = (graph: ReturnType<typeof buildGraph>) => graph.flatMap((stage) => stage.items);

describe('buildGraph', () => {
  it('groups steps by stage and marks unrun steps pending', () => {
    const graph = buildGraph(steps, [], false);
    expect(graph.map((stage) => stage.items.map((node) => node.order))).toEqual([[1, 2], [3]]);
    expect(graph[0].items[0].status).toBe('pending');
  });

  it('marks every step running while a run is in flight', () => {
    expect(nodesOf(buildGraph(steps, [], true)).every((node) => node.status === 'running')).toBe(
      true,
    );
  });

  it('marks steps with a result done and reports the output length', () => {
    const [first] = buildGraph(steps, [result(1, 1, false)], false);
    expect(first.items[0]).toMatchObject({ status: 'done', outputLength: 5 });
    expect(first.items[1]).toMatchObject({ status: 'pending', outputLength: null });
  });

  it('predicts outputs before a run and takes them from the results after', () => {
    const marked = [step(1, 1, true), step(2, 2)];
    expect(nodesOf(buildGraph(marked, [], false)).map((node) => node.isOutput)).toEqual([
      true,
      false,
    ]);
    const ran = [result(1, 1, false), result(2, 2, true)];
    expect(nodesOf(buildGraph(marked, ran, false)).map((node) => node.isOutput)).toEqual([
      false,
      true,
    ]);
  });
});
