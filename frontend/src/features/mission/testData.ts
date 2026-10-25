import { vi } from 'vitest';

import type {
  AgentTool,
  FileListing,
  GeneratedPipelineResponse,
  MissionTemplate,
  Pipeline,
  PipelineStep,
  RevisedPipelineResponse,
  Run,
} from '../../core/api/types';
import { json, makeRun, runStep } from '../runs/testData';

export { json, makeRun, runStep };

/** Shared by the mission tests: a two-agent team whose second agent delivers. */
export function planStep(order: number, stage: number, title: string, isOutput: boolean) {
  const step: PipelineStep = {
    order,
    stage,
    title,
    is_output: isOutput,
    expected_output: `${title} result`,
    prompt: `${title} for {company}: {input}`,
    model: 'vendor/fast',
    role: order === 1 ? 'Researcher' : 'Analyst',
    allowed_tools: order === 1 ? [] : null,
  };
  return step;
}

export const PLAN: Pipeline = {
  name: 'Competitor brief',
  inputs: [{ name: 'company', label: 'Your company', description: 'What your company does' }],
  steps: [planStep(1, 1, 'Market research', false), planStep(2, 2, 'Comparison', true)],
};

export const SAVED: Pipeline = { ...PLAN, id: 7 };

export const GENERATED: GeneratedPipelineResponse = {
  generated_pipeline: PLAN,
  available_models: ['vendor/fast', 'vendor/smart'],
};

/** Revising `base` as "add a fact checker": one added step, the rest copied. */
export function revisionOf(base: Pipeline): RevisedPipelineResponse {
  return {
    revised_pipeline: { ...base, steps: [...base.steps, planStep(3, 3, 'Fact check', true)] },
    changes: [{ target: 'step', kind: 'added', label: 'Fact check', order: 3, fields: [] }],
    available_models: ['vendor/fast', 'vendor/smart'],
  };
}

export const MODELS = { models: ['vendor/fast', 'vendor/smart'], default: 'vendor/fast' };

export const TOOLS: AgentTool[] = [
  { name: 'web_search', description: 'Search the web', source: 'AIMIx' },
];

export const TEMPLATE: MissionTemplate = {
  slug: 'document-digest',
  title: 'Document digest',
  category: 'Research',
  description: 'Summarise a long document.',
  inputs: [{ name: 'document', label: 'Document', description: '' }],
  step_count: 2,
  stage_count: 2,
};

export const FILES: FileListing = {
  files: [
    { path: 'reports/brief.pdf', size: 52_000, modified_at: '2026-10-24T10:00:00Z', type: 'pdf' },
    { path: 'notes.txt', size: 800, modified_at: '2026-10-23T10:00:00Z', type: 'txt' },
  ],
  used_bytes: 52_800,
  quota_bytes: 10_000_000,
  max_file_bytes: 1_000_000,
  allowed_extensions: ['.pdf', '.txt'],
};

/** A finished run of `SAVED` (so it ran exactly the team on screen). */
export function finishedRun(overrides: Partial<Run> = {}): Run {
  return makeRun({
    id: 9,
    pipeline_id: 7,
    pipeline_name: 'Competitor brief',
    status: 'succeeded',
    finished_at: '2026-10-24T10:00:08Z',
    definition: { name: SAVED.name, inputs: SAVED.inputs, steps: SAVED.steps },
    inputs: { company: 'Acme' },
    steps: [
      { ...runStep(1, 'succeeded', 'Research notes'), title: 'Market research', is_output: false },
      { ...runStep(2, 'succeeded', '## Comparison table\n\nAcme wins.'), title: 'Comparison' },
    ],
    ...overrides,
  });
}

type Reply = unknown;
type Routes = Record<string, Reply | ((init: RequestInit | undefined) => Reply | Promise<Reply>)>;

export interface RecordedCall {
  method: string;
  path: string;
  body: unknown;
}

/** A body JSON can carry, as the stand-in server reads it. */
function bodyOf(init: RequestInit | undefined): unknown {
  return typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
}

/**
 * A fetch stand-in for the whole workspace. Each key is "METHOD /api/path" (add the
 * query to match it exactly; without it any query matches). A value is the JSON body, a
 * ready `Response` (built fresh by a function when it must be read twice), or a function
 * of the request that returns either. An unlisted call is a 404, and is recorded.
 */
export function routeFetch(routes: Routes) {
  const calls: RecordedCall[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const href = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, 'http://localhost');
    const method = init?.method ?? 'GET';
    const path = `${url.pathname}${url.search}`;
    calls.push({ method, path, body: bodyOf(init) });
    const key = [`${method} ${path}`, `${method} ${url.pathname}`].find((entry) => entry in routes);
    if (key === undefined) return json({ error: 'not_found', detail: `No route: ${method} ${path}` }, 404);
    const reply = routes[key];
    const value = typeof reply === 'function' ? await reply(init) : reply;
    return value instanceof Response ? value : json(value);
  });
  return {
    calls,
    /** The calls made to `path` (query ignored) with `method`. */
    to: (method: string, path: string) =>
      calls.filter((call) => call.method === method && call.path.split('?')[0] === path),
  };
}

/** Never answers, but fails as a browser does once the request's signal aborts. */
export function hangUntilAborted(init: RequestInit | undefined): Promise<never> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () =>
      reject(new DOMException('The operation was aborted.', 'AbortError')),
    );
  });
}

/** What every mission needs from the server apart from its own routes. */
export const COMMON_ROUTES: Routes = {
  'GET /api/models': MODELS,
  'GET /api/agent-tools': TOOLS,
  'GET /api/templates': [TEMPLATE],
  'GET /api/pipelines/': [],
  'GET /api/files': FILES,
  'GET /api/runs': { items: [], total: 0 },
};

/** Echoes a saved pipeline back as the server would: the body, with an id. */
export function storeAs(id: number) {
  return (init: RequestInit | undefined) => ({ ...(bodyOf(init) as Pipeline), id });
}
