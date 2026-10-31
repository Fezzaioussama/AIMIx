import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MissionPlanResponse, PlanAnswer } from '../../core/api/types';
import type { MissionMessage, QuestionsMessage } from './missionMessages';
import type { StoredMission } from './missionStorage';
import { SKIP_SAID } from './QuestionsMessageView';
import { COMMON_ROUTES, GENERATED, routeFetch } from './testData';
import { useMission } from './useMission';

const NOTHING: StoredMission = { messages: [], draft: null };
const ASKED: MissionPlanResponse = {
  generated_pipeline: null,
  questions: [
    { question: 'Who reads it?', options: ['Students', 'Managers'] },
    { question: 'Which format?', options: [] },
  ],
  available_models: ['vendor/fast'],
};
const STUDENTS: PlanAnswer[] = [{ question: 'Who reads it?', answer: 'Students' }];

/** The planner asks first, then plans once it has answers or may not ask. */
function planner() {
  return routeFetch({
    ...COMMON_ROUTES,
    'POST /api/pipelines/generate': (init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { may_ask: boolean };
      return body.may_ask ? ASKED : { ...GENERATED, questions: [] };
    },
  });
}

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/mission']}>{children}</MemoryRouter>;
}

function kinds(messages: MissionMessage[]): string[] {
  return messages.map((message) => (message.from === 'you' ? 'you' : message.kind));
}

async function askedAbout(description: string) {
  const server = planner();
  const hook = renderHook(() => useMission(undefined, NOTHING), { wrapper });
  act(() => {
    hook.result.current.send(description);
  });
  await waitFor(() =>
    expect(kinds(hook.result.current.conversation.messages)).toContain('questions'),
  );
  const asked = hook.result.current.conversation.messages[1] as QuestionsMessage;
  return { server, hook, asked };
}

describe('useMission: the planner’s questions', () => {
  afterEach(() => vi.restoreAllMocks());

  it('asks before building a team, then builds it from the answers', async () => {
    const { server, hook, asked } = await askedAbout('Write a report');

    expect(asked).toMatchObject({ state: 'open', description: 'Write a report' });
    expect(hook.result.current.team.pipeline).toBeNull();
    expect(server.to('POST', '/api/pipelines/generate')[0].body).toEqual({
      description: 'Write a report',
      may_ask: true,
      answers: [],
    });

    act(() => hook.result.current.answer(asked, STUDENTS, 'Who reads it? — Students'));
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    const { messages } = hook.result.current.conversation;
    expect(kinds(messages)).toEqual(['you', 'questions', 'you', 'team']);
    expect(messages[1]).toMatchObject({ state: 'answered' });
    expect(messages[2]).toMatchObject({ text: 'Who reads it? — Students' });
    expect(server.to('POST', '/api/pipelines/generate')[1].body).toEqual({
      description: 'Write a report',
      may_ask: false,
      answers: STUDENTS,
    });
  });

  it('takes a typed message as the answer to every open question', async () => {
    const { server, hook } = await askedAbout('Write a report');

    act(() => {
      expect(hook.result.current.send('For students, as a PDF')).toBe(true);
    });
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    expect(server.to('POST', '/api/pipelines/generate')[1].body).toEqual({
      description: 'Write a report',
      may_ask: false,
      answers: [{ question: 'Who reads it?\nWhich format?', answer: 'For students, as a PDF' }],
    });
  });

  it('skips the questions: plans without answers and asks nothing more', async () => {
    const { server, hook, asked } = await askedAbout('Write a report');

    act(() => hook.result.current.answer(asked, [], SKIP_SAID));
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());

    expect(hook.result.current.conversation.messages[1]).toMatchObject({ state: 'skipped' });
    expect(server.to('POST', '/api/pipelines/generate')[1].body).toEqual({
      description: 'Write a report',
      may_ask: false,
      answers: [],
    });
  });

  it('answers a set of questions only once', async () => {
    const { server, hook, asked } = await askedAbout('Write a report');

    act(() => hook.result.current.answer(asked, STUDENTS, 'Students'));
    await waitFor(() => expect(hook.result.current.team.pipeline).not.toBeNull());
    act(() => hook.result.current.answer(asked, STUDENTS, 'Students'));

    expect(server.to('POST', '/api/pipelines/generate')).toHaveLength(2);
  });
});
