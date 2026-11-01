import { act, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PLAN_DOCUMENT_EXCERPT_CHARS } from '../../core/api/pipelines';
import { COMMON_ROUTES, GENERATED, deferred, json, routeFetch } from './testData';
import { NOTE, attach, readByName, renderMission, report } from './testDocuments';

describe('useMission: documents for the planner', () => {
  afterEach(() => vi.restoreAllMocks());

  it('plans with the start of each document read, and names them on the message', async () => {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': readByName(),
      'POST /api/pipelines/generate': GENERATED,
    });
    const hook = renderMission();
    await attach(hook, ['report.pdf', 'bad.pdf'], ['read', 'failed']);

    act(() => {
      hook.result.current.send('Summarise these for the board');
    });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    expect(server.to('POST', '/api/pipelines/generate')[0].body).toEqual({
      description: 'Summarise these for the board',
      may_ask: true,
      answers: [],
      documents: [{ ...NOTE, excerpt: 'x'.repeat(PLAN_DOCUMENT_EXCERPT_CHARS) }],
    });
    expect(hook.result.current.conversation.messages[0]).toEqual({
      id: expect.any(String),
      from: 'you',
      text: 'Summarise these for the board',
      documents: [NOTE],
    });
    // They stay with the mission for its run.
    expect(hook.result.current.documents.items.map((item) => item.source)).toEqual([
      'report.pdf',
      'bad.pdf',
    ]);
  });

  it('waits for a document still being read before it plans', async () => {
    const slow = deferred<Response>();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': readByName(slow),
      'POST /api/pipelines/generate': GENERATED,
    });
    const hook = renderMission();
    await attach(hook, ['slow.pdf'], ['reading']);
    expect(hook.result.current.planWaitsFor).toBe('slow.pdf');

    let sent = true;
    act(() => {
      sent = hook.result.current.send('Summarise this report for the board');
    });
    expect(sent).toBe(false);
    expect(hook.result.current.conversation.messages).toEqual([]);

    slow.resolve(json({ ...report, filename: 'slow.pdf' }));
    await waitFor(() => expect(hook.result.current.planWaitsFor).toBe(''));
    act(() => {
      hook.result.current.send('Summarise this report for the board');
    });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    const planned = server.to('POST', '/api/pipelines/generate');
    expect(planned).toHaveLength(1);
    expect(planned[0].body).toMatchObject({ documents: [{ name: 'slow.pdf' }] });
  });

  it('waits for it before answering the planner’s questions too', async () => {
    const slow = deferred<Response>();
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': readByName(slow),
      'POST /api/pipelines/generate': {
        generated_pipeline: null,
        questions: [{ question: 'Who?', options: [] }],
        available_models: [],
      },
    });
    const hook = renderMission();
    act(() => {
      hook.result.current.send('Write a report');
    });
    await waitFor(() => expect(hook.result.current.conversation.messages).toHaveLength(2));
    await attach(hook, ['slow.pdf'], ['reading']);
    const asked = hook.result.current.conversation.messages[1];

    act(() => {
      if (asked.from === 'aimix' && asked.kind === 'questions') {
        hook.result.current.answer(asked, [], 'Skip');
      }
    });

    expect(hook.result.current.conversation.messages).toHaveLength(2);
    expect(server.to('POST', '/api/pipelines/generate')).toHaveLength(1);
  });

  it('sends them with the answers to the planner’s questions too', async () => {
    const server = routeFetch({
      ...COMMON_ROUTES,
      'POST /api/documents/extract': readByName(),
      'POST /api/pipelines/generate': (init: RequestInit | undefined) =>
        JSON.parse(String(init?.body)).may_ask
          ? {
              generated_pipeline: null,
              questions: [{ question: 'Who?', options: [] }],
              available_models: [],
            }
          : GENERATED,
    });
    const hook = renderMission();
    act(() => {
      hook.result.current.send('Write a report');
    });
    await waitFor(() => expect(hook.result.current.conversation.messages).toHaveLength(2));
    await attach(hook, ['report.pdf'], ['read']);

    act(() => {
      hook.result.current.send('The board');
    });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    const [first, second] = server.to('POST', '/api/pipelines/generate');
    expect(first.body).not.toHaveProperty('documents');
    expect(second.body).toMatchObject({ may_ask: false, documents: [{ name: 'report.pdf' }] });
  });
});
