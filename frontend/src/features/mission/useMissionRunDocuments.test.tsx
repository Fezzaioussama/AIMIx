import { act, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import { RUN_INPUT_MAX_LENGTH, runInputSize } from '../pipelines/pipelineInputs';
import {
  COMMON_ROUTES,
  PLAN,
  SAVED,
  deferred,
  hangUntilAborted,
  json,
  revisionOf,
  routeFetch,
} from './testData';
import {
  BLOCK,
  NOTE,
  TEXT,
  attach,
  documentsInput,
  readByName,
  renderMission,
  report,
  withInputs,
} from './testDocuments';
import { NO_TEAM_YET } from './useMissionRun';

/** A second input that is not meant for documents either. */
const focusInput = { name: 'focus', label: 'What to focus on', description: '' };
const TWO_OTHERS = [...PLAN.inputs, focusInput];

describe('useMission: documents for the run', () => {
  afterEach(() => vi.restoreAllMocks());

  it('Run it puts them in the input meant for them, then empties the box', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName() });
    const hook = renderMission(withInputs([...PLAN.inputs, documentsInput]));
    await attach(hook, ['report.pdf', 'bad.pdf'], ['read', 'failed']);

    act(() => hook.result.current.runIt());

    const { run, documents, conversation } = hook.result.current;
    expect(run.formId).not.toBeNull();
    expect(run.draft.values).toEqual({ [DOCUMENTS_INPUT_NAME]: BLOCK });
    expect(documents.items).toEqual([]);
    expect(conversation.messages.at(-2)).toMatchObject({ text: 'Run it', documents: [NOTE] });
  });

  it('puts them in the only input of a team that has one, as there is nowhere else', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName() });
    const hook = renderMission(withInputs(PLAN.inputs));
    await attach(hook, ['report.pdf'], ['read']);

    act(() => hook.result.current.runIt());

    const { run, documents, conversation, placement } = hook.result.current;
    expect(run.draft.values).toEqual({ company: BLOCK });
    expect(documents.items).toEqual([]);
    expect(placement).toBeNull();
    expect(conversation.messages.at(-2)).toMatchObject({ text: 'Run it', documents: [NOTE] });
  });

  it('else keeps them in the box until the person picks the input they go in', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName() });
    const hook = renderMission(withInputs(TWO_OTHERS));
    await attach(hook, ['report.pdf'], ['read']);

    act(() => hook.result.current.runIt());

    expect(hook.result.current.run.formId).not.toBeNull();
    // Never guessed: neither "Your company" nor "What to focus on" is where a report goes.
    expect(hook.result.current.run.draft.values).toEqual({});
    expect(hook.result.current.documents.read).toEqual([report]);
    expect(hook.result.current.conversation.messages.at(-2)).not.toHaveProperty('documents');
    expect(hook.result.current.placement).toMatchObject({
      names: ['report.pdf'],
      choices: TWO_OTHERS,
    });

    act(() => hook.result.current.placement?.place('company'));

    expect(hook.result.current.run.draft.values).toEqual({ company: BLOCK });
    expect(hook.result.current.documents.items).toEqual([]);
    expect(hook.result.current.placement).toBeNull();
  });

  it('puts in only what fits in one run, and keeps the rest for the next', async () => {
    const LONG = 'y'.repeat(120_000);
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': (init: RequestInit | undefined) => ({
        ...report,
        filename: ((init?.body as FormData).get('file') as File).name,
        text: LONG,
        characters: LONG.length,
      }),
    });
    const inputs = [...PLAN.inputs, documentsInput];
    const hook = renderMission(withInputs(inputs));
    const names = ['a.pdf', 'b.pdf', 'c.pdf', 'd.pdf', 'e.pdf'];
    await attach(
      hook,
      names,
      names.map(() => 'read'),
    );

    act(() => hook.result.current.runIt());

    const { run, documents, conversation, placement } = hook.result.current;
    expect(runInputSize(inputs, run.draft)).toBeLessThanOrEqual(RUN_INPUT_MAX_LENGTH);
    expect(run.draft.values[DOCUMENTS_INPUT_NAME]).toContain('[Document: d.pdf]');
    expect(documents.read.map((document) => document.filename)).toEqual(['e.pdf']);
    expect(conversation.messages.at(-2)).toMatchObject({
      documents: names.slice(0, 4).map((name) => ({ name })),
    });
    expect(placement).toEqual({ names: ['e.pdf'], choices: [], place: expect.any(Function) });
  });

  it('else in the free text, and typing "run it" does the same', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName() });
    const hook = renderMission(withInputs([]));
    await attach(hook, ['report.pdf'], ['read']);

    act(() => {
      hook.result.current.send('run it');
    });

    expect(hook.result.current.run.draft.text).toBe(BLOCK);
    expect(hook.result.current.documents.items).toEqual([]);
  });

  it('puts a document read while the form is open straight into it, and the form waits for it', async () => {
    const slow = deferred<Response>();
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName(slow) });
    const hook = renderMission(withInputs([...PLAN.inputs, documentsInput]));
    await attach(hook, ['slow.pdf'], ['reading']);
    act(() => hook.result.current.runIt());
    expect(hook.result.current.run.draft.values).toEqual({});
    expect(hook.result.current.runWaitsFor).toBe('slow.pdf');

    slow.resolve(json({ ...report, filename: 'slow.pdf' }));

    await waitFor(() =>
      expect(hook.result.current.run.draft.values[DOCUMENTS_INPUT_NAME]).toBe(
        `[Document: slow.pdf]\n${TEXT}`,
      ),
    );
    expect(hook.result.current.documents.items).toEqual([]);
    expect(hook.result.current.runWaitsFor).toBe('');
  });

  it('does not make the form wait for a document it would not get', async () => {
    const slow = deferred<Response>();
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName(slow) });
    const hook = renderMission(withInputs(TWO_OTHERS));
    await attach(hook, ['slow.pdf'], ['reading']);
    act(() => hook.result.current.runIt());
    expect(hook.result.current.runWaitsFor).toBe('');

    slow.resolve(json({ ...report, filename: 'slow.pdf' }));

    await waitFor(() => expect(hook.result.current.placement?.names).toEqual(['slow.pdf']));
    expect(hook.result.current.run.draft.values).toEqual({});
  });

  it('asks for the documents again when the form needs them and the box has none', async () => {
    routeFetch(COMMON_ROUTES);
    const hook = renderMission(withInputs([...PLAN.inputs, documentsInput]));

    act(() => hook.result.current.runIt());

    expect(hook.result.current.documentsGone).toBe(true);
    act(() =>
      hook.result.current.run.setDraft({
        text: '',
        values: { [DOCUMENTS_INPUT_NAME]: 'pasted text' },
      }),
    );
    expect(hook.result.current.documentsGone).toBe(false);
  });

  it('keeps them when no form can open', async () => {
    routeFetch({ ...COMMON_ROUTES, 'POST /api/documents/extract': readByName() });
    const hook = renderMission();
    await attach(hook, ['report.pdf'], ['read']);

    act(() => hook.result.current.runIt());

    expect(hook.result.current.conversation.messages.at(-1)).toMatchObject({ text: NO_TEAM_YET });
    expect(hook.result.current.conversation.messages.at(-2)).not.toHaveProperty('documents');
    expect(hook.result.current.documents.read).toEqual([report]);
  });

  it('keeps them through a change request, which does not read them', async () => {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'GET /api/pipelines/7/': SAVED,
      'POST /api/pipelines/revise': revisionOf(SAVED),
      'POST /api/documents/extract': readByName(),
    });
    const hook = renderMission(
      { messages: [{ id: 'n', from: 'you', text: 'hi' }], draft: null },
      7,
    );
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());
    await attach(hook, ['report.pdf'], ['read']);

    act(() => {
      hook.result.current.send('Add a fact checker');
    });
    await waitFor(() => expect(hook.result.current.proposals.revision.proposal).not.toBeNull());

    expect(hook.result.current.conversation.messages.at(-2)).not.toHaveProperty('documents');
    expect(server.to('POST', '/api/pipelines/revise')[0].body).not.toHaveProperty('documents');
    expect(hook.result.current.documents.read).toEqual([report]);
  });

  it('cancels what is still being read when the screen is left', async () => {
    let signal: AbortSignal | null | undefined;
    routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': (init: RequestInit | undefined) => {
        signal = init?.signal;
        return hangUntilAborted(init);
      },
    });
    const hook = renderMission();
    await attach(hook, ['big.pdf'], ['reading']);
    await waitFor(() => expect(signal).toBeDefined());

    hook.unmount();

    expect(signal?.aborted).toBe(true);
  });
});
