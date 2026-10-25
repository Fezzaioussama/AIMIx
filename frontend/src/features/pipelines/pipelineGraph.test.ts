import { describe, expect, it } from 'vitest';

import type { PipelineStep, RunStep, StepResult } from '../../core/api/types';
import { buildGraph, liveNodeStatus } from './pipelineGraph';

/** A followed run's step that has used no tokens, and went through no review round. */
const UNUSED = { input_tokens: 0, output_tokens: 0, cost_usd: null, rounds: 1, verdict: null };

function step(order: number, stage: number, isOutput = false): PipelineStep {
  return {
    order,
    stage,
    title: '',
    is_output: isOutput,
    expected_output: '',
    prompt: 'p',
    model: 'v/m',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  };
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
    tool_calls: [],
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

  it('carries each step expected output for its summary', () => {
    const planned = [{ ...step(1, 1), expected_output: 'One tweet' }];
    expect(nodesOf(buildGraph(planned, [], false))[0].expectedOutput).toBe('One tweet');
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

  it('shows each step of a followed run in its own status', () => {
    const live: RunStep[] = [
      {
        ...result(1, 1, false),
        ...UNUSED,
        status: 'succeeded',
        error: null,
        started_at: null,
        finished_at: null,
      },
      {
        ...result(2, 1, false),
        ...UNUSED,
        status: 'failed',
        error: null,
        started_at: null,
        finished_at: null,
      },
      {
        ...result(3, 2, true),
        ...UNUSED,
        status: 'pending',
        error: null,
        started_at: null,
        finished_at: null,
      },
    ];
    const statuses = (active: boolean) =>
      nodesOf(buildGraph(steps, [live[0]], active, live)).map((node) => node.status);

    expect(statuses(true)).toEqual(['done', 'failed', 'waiting']);
    // Once the run has ended, a step it never reached did not run.
    expect(statuses(false)).toEqual(['done', 'failed', 'pending']);
    expect(nodesOf(buildGraph(steps, [live[0]], true, live)).map((node) => node.isOutput)).toEqual([
      false,
      false,
      true,
    ]);
  });
});

describe('liveNodeStatus', () => {
  it('maps a run step to how the diagram shows it', () => {
    const base = {
      ...result(1, 1, false),
      ...UNUSED,
      error: null,
      started_at: null,
      finished_at: null,
    };
    expect(liveNodeStatus({ ...base, status: 'running' }, true)).toBe('running');
    expect(liveNodeStatus({ ...base, status: 'cancelled' }, false)).toBe('stopped');
    expect(liveNodeStatus({ ...base, status: 'pending' }, true)).toBe('waiting');
  });
});
