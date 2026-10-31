import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MissionMessage } from './missionMessages';
import { note, you } from './missionMessages';
import {
  forgetAllMissions,
  forgetMission,
  MAX_STORED_MESSAGES,
  missionKey,
  readMission,
  restoreMission,
  writeMission,
} from './missionStorage';
import { PLAN } from './testData';
import { describeTeam } from './teamBrief';

describe('mission storage', () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('keeps a mission per pipeline, and one for a mission never saved', () => {
    expect(missionKey(7)).not.toBe(missionKey());
    writeMission(missionKey(7), { messages: [you('hello')], draft: null });
    writeMission(missionKey(), { messages: [], draft: PLAN });

    expect(readMission(missionKey(7)).messages).toHaveLength(1);
    expect(readMission(missionKey(7)).draft).toBeNull();
    expect(readMission(missionKey()).draft).toEqual(PLAN);
    expect(readMission(missionKey(8))).toEqual({ messages: [], draft: null });
  });

  it('round-trips every kind of message', () => {
    const messages: MissionMessage[] = [
      you('Compare my competitors'),
      note('Something went wrong', 'error'),
      { id: 't', from: 'aimix', kind: 'team', origin: 'generated', brief: describeTeam(PLAN) },
      {
        id: 'q',
        from: 'aimix',
        kind: 'questions',
        state: 'open',
        description: 'Write a report',
        questions: [{ question: 'Who reads it?', options: ['Students'] }],
      },
      { id: 'p', from: 'aimix', kind: 'proposal', state: 'applied', changes: [], error: '' },
      { id: 'i', from: 'aimix', kind: 'inputs', state: 'open' },
      { id: 'r', from: 'aimix', kind: 'run', runId: 4 },
    ];

    writeMission(missionKey(7), { messages, draft: null });

    expect(readMission(missionKey(7)).messages).toEqual(messages);
  });

  it('drops what it cannot trust instead of failing', () => {
    window.sessionStorage.setItem(
      missionKey(7),
      JSON.stringify({
        messages: [
          you('kept'),
          { id: 'x', from: 'aimix', kind: 'unknown' },
          { id: 'y', from: 'aimix', kind: 'run', runId: 'four' },
          { id: 'z', from: 'aimix', kind: 'proposal', state: 'bogus', changes: [], error: '' },
          { from: 'you', text: 'no id' },
          'junk',
          null,
        ],
        draft: { name: 3 },
      }),
    );

    const stored = readMission(missionKey(7));

    expect(stored.messages.map((message) => message.id)).toEqual([expect.any(String)]);
    expect(stored.messages[0]).toMatchObject({ from: 'you', text: 'kept' });
    expect(stored.draft).toBeNull();
  });

  it('gives a draft kept before conditions and review loops existed their defaults', () => {
    const { condition: _c, review: _r, ...older } = PLAN.steps[0];
    window.sessionStorage.setItem(
      missionKey(),
      JSON.stringify({ messages: [], draft: { ...PLAN, steps: [older] } }),
    );

    const { draft } = readMission(missionKey());

    expect(draft?.steps[0]).toMatchObject({ condition: null, review: null });
  });

  it('keeps a draft’s condition and review loop', () => {
    const flow = [
      { ...PLAN.steps[0] },
      {
        ...PLAN.steps[1],
        condition: { source: 'step:1', operator: 'contains', value: 'blog' },
        review: { send_back_to_stage: 1, max_rounds: 2 },
      },
    ];
    writeMission(missionKey(), { messages: [], draft: { ...PLAN, steps: flow as never } });

    expect(readMission(missionKey()).draft?.steps[1]).toMatchObject({
      condition: { source: 'step:1', operator: 'contains', value: 'blog' },
      review: { send_back_to_stage: 1, max_rounds: 2 },
    });
  });

  it('drops a draft whose condition or review is not what the screen reads', () => {
    for (const damaged of [{ condition: 'blog' }, { review: { max_rounds: 'two' } }]) {
      window.sessionStorage.setItem(
        missionKey(),
        JSON.stringify({
          messages: [],
          draft: { ...PLAN, steps: [{ ...PLAN.steps[0], ...damaged }] },
        }),
      );

      expect(readMission(missionKey()).draft).toBeNull();
    }
  });

  it('drops an answer whose inner parts are not what the screen draws', () => {
    const brief = describeTeam(PLAN);
    const damaged: unknown[] = [
      // an agent without its tools, as an older version might have written it
      {
        id: 'a',
        from: 'aimix',
        kind: 'team',
        origin: 'generated',
        brief: { ...brief, agents: [{ order: 1, name: 'x' }] },
      },
      {
        id: 'b',
        from: 'aimix',
        kind: 'team',
        origin: 'generated',
        brief: { ...brief, stages: 'two' },
      },
      {
        id: 'c',
        from: 'aimix',
        kind: 'team',
        origin: 'generated',
        brief: { ...brief, provides: [1] },
      },
      // a change without its fields
      {
        id: 'd',
        from: 'aimix',
        kind: 'proposal',
        state: 'applied',
        changes: [{ label: 'x' }],
        error: '',
      },
      // questions without their suggested answers, or about no mission
      {
        id: 'f',
        from: 'aimix',
        kind: 'questions',
        state: 'open',
        description: 'x',
        questions: [{ question: 'Who?' }],
      },
      { id: 'g', from: 'aimix', kind: 'questions', state: 'open', questions: [] },
      { id: 'e', from: 'aimix', kind: 'note', text: 'kept', tone: 'info' },
    ];
    window.sessionStorage.setItem(
      missionKey(7),
      JSON.stringify({ messages: damaged, draft: null }),
    );

    expect(readMission(missionKey(7)).messages.map((message) => message.id)).toEqual(['e']);
  });

  it('keeps a draft team only when its steps and inputs are whole', () => {
    const broken = { ...PLAN, steps: [{ ...PLAN.steps[0], prompt: undefined }] };
    window.sessionStorage.setItem(missionKey(), JSON.stringify({ messages: [], draft: broken }));
    expect(readMission(missionKey()).draft).toBeNull();

    window.sessionStorage.setItem(
      missionKey(),
      JSON.stringify({ messages: [], draft: { ...PLAN, inputs: [{ name: 'x' }] } }),
    );
    expect(readMission(missionKey()).draft).toBeNull();

    writeMission(missionKey(), { messages: [], draft: PLAN });
    expect(readMission(missionKey()).draft).toEqual(PLAN);
  });

  it('starts empty when the stored text is not JSON', () => {
    window.sessionStorage.setItem(missionKey(7), '{not json');

    expect(readMission(missionKey(7))).toEqual({ messages: [], draft: null });
  });

  it('keeps only the newest messages', () => {
    const many = Array.from({ length: MAX_STORED_MESSAGES + 25 }, (_, index) => you(`m${index}`));

    writeMission(missionKey(7), { messages: many, draft: null });

    const kept = readMission(missionKey(7)).messages;
    expect(kept).toHaveLength(MAX_STORED_MESSAGES);
    expect(kept[kept.length - 1]).toMatchObject({ text: `m${many.length - 1}` });
  });

  it('forgets a mission', () => {
    writeMission(missionKey(), { messages: [you('hi')], draft: null });

    forgetMission(missionKey());

    expect(readMission(missionKey()).messages).toEqual([]);
  });

  it('forgets every mission at once, and nothing else the tab keeps', () => {
    writeMission(missionKey(), { messages: [you('a draft')], draft: PLAN });
    writeMission(missionKey(7), { messages: [you('hi')], draft: null });
    writeMission(missionKey(8), { messages: [you('hello')], draft: null });
    window.sessionStorage.setItem('another.key', 'kept');

    forgetAllMissions();

    for (const key of [missionKey(), missionKey(7), missionKey(8)]) {
      expect(window.sessionStorage.getItem(key)).toBeNull();
    }
    expect(restoreMission()).toEqual({ messages: [], draft: null });
    expect(window.sessionStorage.getItem('another.key')).toBe('kept');
  });

  it('works without storage: blocked reads and writes only mean nothing is kept', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(() => writeMission(missionKey(7), { messages: [you('hi')], draft: null })).not.toThrow();
    expect(readMission(missionKey(7))).toEqual({ messages: [], draft: null });
    expect(() => forgetMission(missionKey(7))).not.toThrow();
  });

  it('forgets quietly when the storage refuses to let go', () => {
    writeMission(missionKey(7), { messages: [you('hi')], draft: null });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(() => forgetAllMissions()).not.toThrow();
  });

  it('says so when the page was left before AIMIx answered', () => {
    writeMission(missionKey(7), { messages: [you('Make it shorter')], draft: null });

    const { messages } = restoreMission(7);

    expect(messages).toHaveLength(2);
    expect(messages[1]).toMatchObject({ from: 'aimix', kind: 'note' });
  });

  it('adds nothing when AIMIx had the last word', () => {
    writeMission(missionKey(7), { messages: [you('hi'), note('hello')], draft: null });

    expect(restoreMission(7).messages).toHaveLength(2);
  });
});
