import { act, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { json, makeRun } from '../runs/testData';
import { note, you, type MissionMessage } from './missionMessages';
import type { StoredMission } from './missionStorage';
import { LocationProbe } from './testRender';
import {
  COMMON_ROUTES,
  GENERATED,
  PLAN,
  SAVED,
  TEMPLATE,
  finishedRun,
  hangUntilAborted,
  revisionOf,
  routeFetch,
  storeAs,
} from './testData';
import { useMission } from './useMission';
import { GENERATION_STOPPED } from './useTeamGeneration';
import { NO_TEAM_YET, STILL_RUNNING } from './useMissionRun';

const NOTHING: StoredMission = { messages: [], draft: null };

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={['/mission']}>
      {children}
      <LocationProbe />
    </MemoryRouter>
  );
}

function renderMission(routeId?: number, seed = NOTHING) {
  return renderHook(() => useMission(routeId, seed), { wrapper });
}

/** What AIMIx has said, by kind, in order. */
function kinds(messages: MissionMessage[]): string[] {
  return messages.map((message) => (message.from === 'you' ? 'you' : message.kind));
}

describe('useMission: describing a mission', () => {
  afterEach(() => vi.restoreAllMocks());

  it('turns a description into a team, described in words, without saving it', async () => {
    const server = routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/generate': GENERATED });
    const { result } = renderMission();

    act(() => {
      expect(result.current.send('  Compare my competitors  ')).toBe(true);
    });
    await waitFor(() => expect(result.current.team.pipeline).not.toBeNull());

    const { messages } = result.current.conversation;
    expect(kinds(messages)).toEqual(['you', 'team']);
    expect(messages[0]).toMatchObject({ text: 'Compare my competitors' });
    expect(messages[1]).toMatchObject({
      origin: 'generated',
      brief: { name: 'Competitor brief', stages: 2, provides: ['Your company'] },
    });
    expect(server.to('POST', '/api/pipelines/generate')[0].body).toEqual({
      description: 'Compare my competitors',
      may_ask: true,
      answers: [],
    });
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(0);
    expect(result.current.team.unsaved).toBe(true);
  });

  it('names a plan the planner left unnamed after the description', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': { ...GENERATED, generated_pipeline: { ...PLAN, name: '' } },
    });
    const { result } = renderMission();

    act(() => {
      result.current.send(
        'Summarise the quarterly numbers for the board every Monday morning please',
      );
    });
    await waitFor(() => expect(result.current.team.pipeline).not.toBeNull());

    // The first eight words of the description.
    expect(result.current.team.pipeline?.name).toBe(
      'Summarise the quarterly numbers for the board every',
    );
  });

  it('answers a failed plan in plain words and lets the person try again', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': () =>
        json({ error: 'upstream_response_invalid', detail: 'Invalid JSON: line 1' }, 502),
    });
    const { result } = renderMission();

    act(() => {
      result.current.send('Compare my competitors');
    });
    await waitFor(() => expect(result.current.conversation.messages).toHaveLength(2));

    expect(result.current.conversation.messages[1]).toMatchObject({
      kind: 'note',
      tone: 'error',
      text: 'I could not turn that into a team. Try describing it another way.',
    });
    expect(result.current.team.pipeline).toBeNull();
    expect(result.current.thinking).toBe(false);
    expect(result.current.send('Compare my competitors again')).toBe(true);
  });

  it('stops when asked to, and says so', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/generate': hangUntilAborted });
    const { result } = renderMission();
    act(() => {
      result.current.send('Compare my competitors');
    });
    await waitFor(() => expect(result.current.generation.generating).toBe(true));
    expect(result.current.thinking).toBe(true);
    // Nothing else can be sent while AIMIx is working.
    expect(result.current.send('And another thing')).toBe(false);

    act(() => result.current.generation.cancel());
    await waitFor(() => expect(result.current.generation.generating).toBe(false));

    expect(result.current.conversation.messages.at(-1)).toMatchObject({
      kind: 'note',
      text: GENERATION_STOPPED,
    });
  });

  it('cancels the request and says nothing when the screen is left', async () => {
    let signal: AbortSignal | null | undefined;
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': (init) => {
        signal = init?.signal;
        return hangUntilAborted(init);
      },
    });
    const { result, unmount } = renderMission();
    act(() => {
      result.current.send('Compare my competitors');
    });
    await waitFor(() => expect(result.current.generation.generating).toBe(true));

    unmount();

    expect(signal?.aborted).toBe(true);
  });

  it('ignores an empty message', () => {
    const { result } = renderMission();

    expect(result.current.send('   ')).toBe(false);
    expect(result.current.conversation.messages).toEqual([]);
  });
});

describe('useMission: asking for changes', () => {
  afterEach(() => vi.restoreAllMocks());

  async function savedMission() {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'POST /api/pipelines/revise': revisionOf(SAVED),
      'PUT /api/pipelines/7/': storeAs(7),
    });
    const hook = renderMission(7, { messages: [note('Welcome back')], draft: null });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());
    return { server, ...hook };
  }

  it('answers a change request with a proposal, and changes nothing yet', async () => {
    const { server, result } = await savedMission();

    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.proposal).not.toBeNull());

    expect(kinds(result.current.conversation.messages)).toEqual(['note', 'you', 'proposal']);
    expect(result.current.proposals.revision.proposal?.changes).toHaveLength(1);
    expect(result.current.team.pipeline?.steps).toHaveLength(2);
    expect(result.current.thinking).toBe(false);
    expect(server.to('POST', '/api/pipelines/revise')[0].body).toMatchObject({
      instruction: 'Add an agent that checks the facts',
      pipeline: { name: 'Competitor brief' },
    });
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(0);
  });

  it('applies the proposal: the team changes, and a saved mission is saved', async () => {
    const { server, result } = await savedMission();
    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.proposal).not.toBeNull());

    act(() => result.current.proposals.apply());

    expect(result.current.team.pipeline?.steps).toHaveLength(3);
    expect(result.current.proposals.revision.proposal).toBeNull();
    expect(result.current.conversation.messages.at(-1)).toMatchObject({
      kind: 'proposal',
      state: 'applied',
      changes: [{ label: 'Fact check' }],
    });
    await waitFor(() => expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1));
    expect(
      (server.to('PUT', '/api/pipelines/7/')[0].body as { steps: unknown[] }).steps,
    ).toHaveLength(3);
    await waitFor(() => expect(result.current.team.unsaved).toBe(false));
  });

  it('discards the proposal and leaves the team as it was', async () => {
    const { server, result } = await savedMission();
    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.proposal).not.toBeNull());

    act(() => result.current.proposals.discard());

    expect(result.current.team.pipeline?.steps).toHaveLength(2);
    expect(result.current.conversation.messages.at(-1)).toMatchObject({
      kind: 'proposal',
      state: 'discarded',
    });
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(0);
  });

  it('settles an unanswered proposal when the person asks again', async () => {
    const { result } = await savedMission();
    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.proposal).not.toBeNull());

    act(() => {
      result.current.send('Actually make it shorter');
    });

    const proposals = result.current.conversation.messages.filter(
      (m) => m.from === 'aimix' && m.kind === 'proposal',
    );
    expect(proposals).toHaveLength(2);
    expect(proposals[0]).toMatchObject({ state: 'discarded' });
    expect(proposals[1]).toMatchObject({ state: 'pending' });
  });

  it('keeps a failed change request as an answer', async () => {
    const { result } = await savedMission();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/revise': () =>
        json({ error: 'upstream_response_invalid', detail: 'bad json' }, 502),
    });

    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.error).not.toBe(''));
    act(() => {
      result.current.send('Try something else');
    });

    const [failed] = result.current.conversation.messages.filter(
      (m) => m.from === 'aimix' && m.kind === 'proposal',
    );
    expect(failed).toMatchObject({
      state: 'failed',
      error: 'AIMIx could not turn that into a change. Try saying it another way.',
    });
  });

  it('stops a change request without an error', async () => {
    const { result } = await savedMission();
    routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/revise': hangUntilAborted });
    act(() => {
      result.current.send('Add an agent that checks the facts');
    });
    await waitFor(() => expect(result.current.proposals.revision.busy).toBe(true));
    expect(result.current.thinking).toBe(true);

    act(() => result.current.proposals.revision.cancel());
    await waitFor(() => expect(result.current.proposals.revision.busy).toBe(false));
    act(() => {
      result.current.send('Make it shorter');
    });

    const [stopped] = result.current.conversation.messages.filter(
      (m) => m.from === 'aimix' && m.kind === 'proposal',
    );
    expect(stopped).toMatchObject({ state: 'stopped', error: '' });
  });
});

describe('useMission: running', () => {
  afterEach(() => vi.restoreAllMocks());

  async function newMission() {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/generate': GENERATED,
      'POST /api/pipelines/': storeAs(7),
      'POST /api/pipelines/7/runs': makeRun({ id: 9, pipeline_id: 7, status: 'queued', steps: [] }),
    });
    const hook = renderMission();
    act(() => {
      hook.result.current.send('Compare my competitors');
    });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());
    return { server, ...hook };
  }

  it('asks for the inputs in the conversation when told to run, by phrase or by button', async () => {
    const { result } = await newMission();

    act(() => {
      result.current.send('run it');
    });

    expect(kinds(result.current.conversation.messages)).toEqual(['you', 'team', 'you', 'inputs']);
    expect(result.current.run.formId).toBe(result.current.conversation.messages[3].id);
    expect(result.current.run.newFormId).toBe(result.current.run.formId);

    act(() => result.current.run.ask());

    expect(kinds(result.current.conversation.messages).slice(-2)).toEqual(['you', 'inputs']);
    // Only the newest form can be filled in; the earlier one is closed.
    expect(result.current.conversation.messages[3]).toMatchObject({ state: 'closed' });
  });

  it('saves the new mission on its first run, then starts the run and follows it', async () => {
    const { server, result } = await newMission();
    act(() => result.current.run.ask());
    act(() => result.current.run.setDraft({ text: '', values: { company: 'Acme' } }));

    let started = false;
    await act(async () => {
      started = await result.current.run.start();
    });

    expect(started).toBe(true);
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(1);
    expect(server.to('POST', '/api/pipelines/7/runs')[0].body).toEqual({
      inputs: { company: 'Acme' },
    });
    expect(result.current.followed.run?.id).toBe(9);
    const { messages } = result.current.conversation;
    expect(messages.at(-2)).toMatchObject({ kind: 'inputs', state: 'started' });
    expect(messages.at(-1)).toMatchObject({ kind: 'run', runId: 9 });
    expect(result.current.run.draft).toEqual({ text: '', values: {} });
    // The mission now has an address of its own, and says it is the same workspace.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/mission/7'));
    expect(JSON.parse(screen.getByTestId('location').dataset.state ?? 'null')).toEqual({
      adopted: 7,
    });
  });

  it('saves a saved mission’s edits before running it', async () => {
    const { result } = await newMission();
    await act(async () => {
      await result.current.team.save();
    });
    const server = routeFetch({
      ...COMMON_ROUTES,
      'PUT /api/pipelines/7/': storeAs(7),
      'POST /api/pipelines/7/runs': makeRun({
        id: 10,
        pipeline_id: 7,
        status: 'queued',
        steps: [],
      }),
    });
    act(() => result.current.team.patchStep(1, { role: 'Lead researcher' }));
    act(() => result.current.run.ask());
    act(() => result.current.run.setDraft({ text: '', values: { company: 'Acme' } }));

    await act(async () => {
      await result.current.run.start();
    });

    const writes = server.calls
      .filter((call) => call.method !== 'GET')
      .map((call) => `${call.method} ${call.path}`);
    expect(writes).toEqual(['PUT /api/pipelines/7/', 'POST /api/pipelines/7/runs']);
    expect((server.calls[0].body as { steps: { role: string }[] }).steps[0].role).toBe(
      'Lead researcher',
    );
    expect(result.current.followed.run?.id).toBe(10);
  });

  it('keeps the form and says why when the run does not start', async () => {
    const { result } = await newMission();
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/': storeAs(7),
      'POST /api/pipelines/7/runs': () =>
        json({ error: 'validation_error', detail: 'Fill in “company”.' }, 400),
    });
    act(() => result.current.run.ask());
    act(() => result.current.run.setDraft({ text: '', values: { company: 'Acme' } }));

    let started = true;
    await act(async () => {
      started = await result.current.run.start();
    });

    expect(started).toBe(false);
    expect(result.current.run.error).toBe('Fill in “company”.');
    expect(result.current.run.formId).not.toBeNull();
    expect(result.current.run.starting).toBe(false);
  });

  it('does not start a run when the team could not be saved', async () => {
    const { result } = await newMission();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/pipelines/': () =>
        json({ error: 'validation_error', detail: 'Prompt is empty.' }, 400),
    });
    act(() => result.current.run.ask());

    await act(async () => {
      await result.current.run.start();
    });

    expect(result.current.run.error).toBe('Prompt is empty.');
    expect(server.calls.some((call) => call.path.includes('/runs'))).toBe(false);
  });

  it('asks for a team first when there is none', () => {
    const { result } = renderMission();

    act(() => result.current.run.ask('run it'));

    expect(result.current.conversation.messages.at(-1)).toMatchObject({ text: NO_TEAM_YET });
    expect(result.current.run.formId).toBeNull();
  });
});

describe('useMission: reopening a mission', () => {
  afterEach(() => vi.restoreAllMocks());

  it('loads the team and its newest run, and greets with the team', async () => {
    const run = finishedRun();
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [run], total: 1 },
      'GET /api/runs/9': run,
    });
    const { result } = renderMission(7);

    await waitFor(() => expect(result.current.team.pipeline).toEqual(SAVED));
    await waitFor(() => expect(result.current.followed.run?.id).toBe(9));

    expect(result.current.conversation.messages).toHaveLength(1);
    expect(result.current.conversation.messages[0]).toMatchObject({
      kind: 'team',
      origin: 'reopened',
    });
    // The newest run was of exactly this team, so the graph may show it.
    expect(result.current.followed.shown?.id).toBe(9);
    expect(result.current.unavailable).toBe(false);
  });

  it('says nothing new when the conversation was kept', async () => {
    routeFetch({ ...COMMON_ROUTES, 'GET /api/pipelines/7/': SAVED });
    const { result } = renderMission(7, { messages: [you('hi'), note('hello')], draft: null });

    await waitFor(() => expect(result.current.team.pipeline).not.toBeNull());

    expect(result.current.conversation.messages).toHaveLength(2);
  });

  it('cannot be talked to while loading or when it could not be loaded', async () => {
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': () => json({ error: 'not_found', detail: 'gone' }, 404),
    });
    const { result } = renderMission(7);

    expect(result.current.unavailable).toBe(true);
    expect(result.current.send('Make it shorter')).toBe(false);
    await waitFor(() => expect(result.current.team.error).not.toBe(''));
    expect(result.current.unavailable).toBe(true);
  });

  it('will not start a second run while one is still going', async () => {
    const running = finishedRun({ id: 12, status: 'running', finished_at: null });
    routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'GET /api/runs?limit=1&offset=0&pipeline_id=7': { items: [running], total: 1 },
      'GET /api/runs/12': running,
    });
    const { result } = renderMission(7, { messages: [note('hello')], draft: null });
    await waitFor(() => expect(result.current.followed.active).toBe(true));

    act(() => {
      result.current.send('run it');
    });

    expect(result.current.conversation.messages.at(-1)).toMatchObject({ text: STILL_RUNNING });
    expect(result.current.run.formId).toBeNull();
  });
});

describe('useMission: templates', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts from a template as the person’s own team', () => {
    routeFetch(COMMON_ROUTES);
    const { result } = renderMission();

    act(() => result.current.startFromTemplate(TEMPLATE, SAVED));

    expect(result.current.team.pipeline).toEqual(SAVED);
    expect(result.current.team.unsaved).toBe(false);
    const { messages } = result.current.conversation;
    expect(messages[0]).toMatchObject({
      from: 'you',
      text: expect.stringContaining('Document digest'),
    });
    expect(messages[1]).toMatchObject({ kind: 'team', origin: 'template' });
  });

  it('gives a template’s mission its address at once', async () => {
    routeFetch(COMMON_ROUTES);
    const { result } = renderMission();

    act(() => result.current.startFromTemplate(TEMPLATE, SAVED));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/mission/7'));
  });
});

describe('useMission: opening in the builder', () => {
  afterEach(() => vi.restoreAllMocks());

  it('saves a new mission, then opens it in the builder instead of moving to its own address', async () => {
    const server = routeFetch({ ...COMMON_ROUTES, 'POST /api/pipelines/': storeAs(7) });
    const { result } = renderMission(undefined, { messages: [], draft: PLAN });

    await act(async () => {
      await result.current.openInBuilder();
    });

    const location = screen.getByTestId('location');
    expect(location).toHaveTextContent('/pipeline');
    expect(JSON.parse(location.dataset.state ?? 'null')).toEqual({ pipelineId: 7 });
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(1);
  });
});
