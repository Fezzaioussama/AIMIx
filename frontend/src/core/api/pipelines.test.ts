import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import {
  generatePipeline,
  listPipelines,
  planMission,
  revisePipeline,
  savePipeline,
} from './pipelines';
import type { Pipeline } from './types';

const pipeline: Pipeline = { name: 'Drafts', inputs: [], steps: [] };

describe('savePipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('creates a new pipeline and updates an existing one', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(JSON.stringify(pipeline), {
          headers: { 'Content-Type': 'application/json' },
        }),
    );

    await savePipeline(pipeline);
    await savePipeline({ ...pipeline, id: 7 });

    expect(fetchMock.mock.calls[0][0]).toBe(API.pipelines);
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
    expect(fetchMock.mock.calls[1][0]).toBe(API.pipeline(7));
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PUT');
  });

  it('surfaces an update failure from the API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'not_found', detail: 'Pipeline missing' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(savePipeline({ ...pipeline, id: 7 })).rejects.toMatchObject({
      code: 'not_found',
      message: 'Pipeline missing',
    });
  });
});

describe('pipeline agent fields', () => {
  afterEach(() => vi.restoreAllMocks());

  it('defaults agent fields in older saved pipelines and generated plans', async () => {
    const legacy = {
      name: 'Legacy',
      steps: [{ order: 1, stage: 1, title: '', is_output: false, prompt: 'Work', model: 'v/m' }],
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify([legacy]), { headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ generated_pipeline: legacy, available_models: ['v/m'] }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    const saved = await listPipelines();
    const generated = await generatePipeline('Plan something', 'v/m');

    const defaults = {
      role: '',
      allowed_tools: null,
      expected_output: '',
      condition: null,
      review: null,
    };
    expect(saved[0].inputs).toEqual([]);
    expect(saved[0].steps[0]).toMatchObject(defaults);
    expect(generated.generated_pipeline.inputs).toEqual([]);
    expect(generated.generated_pipeline.steps[0]).toMatchObject(defaults);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('planMission', () => {
  afterEach(() => vi.restoreAllMocks());

  const reply = (body: unknown) =>
    new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

  it('lets the planner ask first, and sends the answers to its questions', async () => {
    const asked = { question: 'Who reads it?', options: ['Students'] };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        reply({ generated_pipeline: null, questions: [asked], available_models: ['v/m'] }),
      );
    const answers = [{ question: 'Who reads it?', answer: 'Students' }];

    const plan = await planMission('A report', answers, false);

    expect(plan).toEqual({
      generated_pipeline: null,
      questions: [asked],
      available_models: ['v/m'],
    });
    expect(fetchMock.mock.calls[0][0]).toBe(API.generatePipeline);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      description: 'A report',
      may_ask: false,
      answers,
    });
  });

  it('gives a planned team the defaults of the fields it omits', async () => {
    const legacy = {
      name: 'L',
      steps: [{ order: 1, stage: 1, title: '', prompt: 'p', model: 'v/m' }],
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      reply({ generated_pipeline: legacy, questions: [], available_models: ['v/m'] }),
    );

    const plan = await planMission('A report', [], true);

    expect(plan.generated_pipeline?.inputs).toEqual([]);
    expect(plan.generated_pipeline?.steps[0]).toMatchObject({ review: null, condition: null });
  });
});

describe('conditions and review loops', () => {
  afterEach(() => vi.restoreAllMocks());

  it('keeps the ones a saved pipeline has', async () => {
    const condition = { source: 'step:1', operator: 'contains', value: 'blog' };
    const review = { send_back_to_stage: 1, max_rounds: 2 };
    const stored = {
      name: 'Flow',
      inputs: [],
      steps: [
        { order: 1, stage: 1, title: '', is_output: false, prompt: 'a', model: 'v/m' },
        { order: 2, stage: 2, title: '', is_output: false, prompt: 'b', model: 'v/m', condition },
        { order: 3, stage: 3, title: '', is_output: false, prompt: 'c', model: 'v/m', review },
      ],
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([stored]), { headers: { 'Content-Type': 'application/json' } }),
    );

    const [saved] = await listPipelines();

    expect(saved.steps.map((step) => step.condition)).toEqual([null, condition, null]);
    expect(saved.steps.map((step) => step.review)).toEqual([null, null, review]);
  });

  it('sends them when a pipeline is saved', async () => {
    const condition = { source: 'previous_output', operator: 'is_empty' as const, value: '' };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(pipeline), { headers: { 'Content-Type': 'application/json' } }),
      );
    const step = {
      order: 1,
      stage: 1,
      title: '',
      is_output: false,
      expected_output: '',
      prompt: 'p',
      model: 'v/m',
      role: '',
      allowed_tools: null,
      condition,
      review: null,
    };

    await savePipeline({ ...pipeline, steps: [step] });

    const sent = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(sent.steps[0].condition).toEqual(condition);
    expect(sent.steps[0].review).toBeNull();
  });
});

describe('revisePipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts the draft and the instruction, and fills in what the planner left out', async () => {
    const sparse = {
      name: 'Revised',
      steps: [{ order: 1, stage: 1, title: '', is_output: false, model: 'v/m' }],
    };
    const body = { revised_pipeline: sparse, changes: [], available_models: [] };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
      );

    const response = await revisePipeline(pipeline, 'Add a step');

    expect(fetchMock.mock.calls[0][0]).toBe(API.revisePipeline);
    expect(fetchMock.mock.calls[0][1]?.body).toBe(
      '{"pipeline":{"name":"Drafts","inputs":[],"steps":[]},"instruction":"Add a step"}',
    );
    expect(response.revised_pipeline.inputs).toEqual([]);
    expect(response.revised_pipeline.steps[0]).toMatchObject({
      prompt: '',
      role: '',
      allowed_tools: null,
      expected_output: '',
      condition: null,
      review: null,
    });
  });
});
