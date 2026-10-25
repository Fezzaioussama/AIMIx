import { describe, expect, it } from 'vitest';

import type { PipelineInput, ScheduleTiming } from '../../core/api/types';
import {
  FREQUENCY_CHOICES,
  browserTimeZone,
  describeTiming,
  draftFromSchedule,
  emptyScheduleDraft,
  formatNextRun,
  hourlyTime,
  minutesOf,
  ordinal,
  scheduleProblem,
  timeZoneName,
  timeZoneOptions,
  timingOf,
  toCreate,
  toPatch,
  withFrequency,
} from './scheduleDraft';
import { NAMED_SCHEDULE, SCHEDULE } from './testData';

const PARIS = 'Europe/Paris';
const TOPIC: PipelineInput = { name: 'topic', label: 'Topic', description: '' };
const AUDIENCE: PipelineInput = { name: 'audience', label: '', description: '' };

function timing(overrides: Partial<ScheduleTiming>): ScheduleTiming {
  return { frequency: 'daily', time: '09:00', timezone: PARIS, ...overrides };
}

describe('describing a timing in words', () => {
  it('says each frequency plainly, with the time zone', () => {
    expect(describeTiming(timing({ frequency: 'daily' }))).toBe('Every day at 09:00, Paris time');
    expect(describeTiming(timing({ frequency: 'weekdays', time: '18:30' }))).toBe(
      'Every weekday at 18:30, Paris time',
    );
    expect(describeTiming(timing({ frequency: 'weekly', weekday: 0 }))).toBe(
      'Every Monday at 09:00, Paris time',
    );
    expect(describeTiming(timing({ frequency: 'weekly', weekday: 6 }))).toBe(
      'Every Sunday at 09:00, Paris time',
    );
    expect(describeTiming(timing({ frequency: 'monthly', day_of_month: 1 }))).toBe(
      'On the 1st of every month at 09:00, Paris time',
    );
  });

  it('says hourly schedules by their minutes, without a zone', () => {
    expect(describeTiming(timing({ frequency: 'hourly', time: '00:00' }))).toBe(
      'Every hour, on the hour',
    );
    expect(describeTiming(timing({ frequency: 'hourly', time: '00:15' }))).toBe(
      'Every hour, 15 minutes past',
    );
    expect(describeTiming(timing({ frequency: 'hourly', time: '00:01' }))).toBe(
      'Every hour, 1 minute past',
    );
  });

  it('warns that a late day of the month falls back to the last day of a short month', () => {
    expect(describeTiming(timing({ frequency: 'monthly', day_of_month: 28 }))).toBe(
      'On the 28th of every month at 09:00, Paris time',
    );
    expect(describeTiming(timing({ frequency: 'monthly', day_of_month: 31 }))).toBe(
      'On the 31st of every month at 09:00, Paris time (or the last day, in shorter months)',
    );
  });

  it('names a time zone by its city', () => {
    expect(timeZoneName(PARIS)).toBe('Paris time');
    expect(timeZoneName('America/New_York')).toBe('New York time');
    expect(timeZoneName('America/Argentina/Buenos_Aires')).toBe('Buenos Aires time');
    expect(timeZoneName('UTC')).toBe('UTC');
    expect(timeZoneName('Etc/UTC')).toBe('UTC');
  });

  it('writes ordinals', () => {
    const days = [1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30, 31].map(ordinal);
    expect(days).toEqual([
      '1st',
      '2nd',
      '3rd',
      '4th',
      '11th',
      '12th',
      '13th',
      '21st',
      '22nd',
      '23rd',
      '30th',
      '31st',
    ]);
  });
});

describe('formatNextRun', () => {
  it('shows the day and time on the schedule’s own clock', () => {
    expect(formatNextRun('2026-10-26T08:00:00Z', PARIS)).toBe('Mon 26 Oct, 09:00');
    expect(formatNextRun('2026-10-26T08:00:00Z', 'America/New_York')).toBe('Mon 26 Oct, 04:00');
    expect(formatNextRun('2026-10-26T23:30:00Z', 'Asia/Tokyo')).toBe('Tue 27 Oct, 08:30');
    expect(formatNextRun('2026-10-26T08:00:00Z', 'UTC')).toBe('Mon 26 Oct, 08:00');
  });

  it('uses a 24-hour clock, with midnight as 00', () => {
    expect(formatNextRun('2026-10-26T23:00:00Z', PARIS)).toBe('Tue 27 Oct, 00:00');
  });

  it('falls back to UTC for a zone this browser does not know', () => {
    expect(formatNextRun('2026-10-26T08:00:00Z', 'Mars/Olympus')).toBe('Mon 26 Oct, 08:00 UTC');
  });
});

describe('time zones', () => {
  it('starts with UTC, lists each zone once, and keeps the current one even if unknown', () => {
    const options = timeZoneOptions('Mars/Olympus');

    expect(options[0]).toBe('UTC');
    expect(options).toContain('Mars/Olympus');
    expect(options).toContain(PARIS);
    expect(new Set(options).size).toBe(options.length);
    expect(options.slice(1)).toEqual([...options.slice(1)].sort());
  });

  it('knows the browser’s own zone', () => {
    expect(timeZoneOptions(browserTimeZone())).toContain(browserTimeZone());
  });
});

describe('the form’s draft', () => {
  it('starts as every Monday at 09:00 on the given clock, asking for nothing yet', () => {
    const draft = emptyScheduleDraft(PARIS);

    expect(draft).toMatchObject({
      frequency: 'weekly',
      time: '09:00',
      weekday: 0,
      timezone: PARIS,
    });
    expect(draft.run).toEqual({ text: '', values: {} });
  });

  it('is read back from a saved schedule', () => {
    expect(draftFromSchedule(NAMED_SCHEDULE)).toEqual({
      frequency: 'weekly',
      time: '09:00',
      weekday: 0,
      dayOfMonth: 1,
      timezone: PARIS,
      run: { text: '', values: { topic: 'bees', audience: 'kids' } },
    });
    expect(
      draftFromSchedule({ ...SCHEDULE, frequency: 'monthly', day_of_month: 15 }),
    ).toMatchObject({
      dayOfMonth: 15,
    });
  });

  it('keeps only the day field its frequency uses', () => {
    const draft = { ...emptyScheduleDraft(PARIS), weekday: 3, dayOfMonth: 9 };

    expect(timingOf({ ...draft, frequency: 'daily' })).toEqual({
      frequency: 'daily',
      time: '09:00',
      timezone: PARIS,
    });
    expect(timingOf({ ...draft, frequency: 'weekly' })).toMatchObject({ weekday: 3 });
    expect(timingOf({ ...draft, frequency: 'weekly' })).not.toHaveProperty('day_of_month');
    expect(timingOf({ ...draft, frequency: 'monthly' })).toMatchObject({ day_of_month: 9 });
    expect(timingOf({ ...draft, frequency: 'monthly' })).not.toHaveProperty('weekday');
  });

  it('changes frequency, keeping the time unless hourly changes what the clock means', () => {
    const draft = { ...emptyScheduleDraft(PARIS), time: '18:45' };

    expect(withFrequency(draft, 'monthly')).toMatchObject({ frequency: 'monthly', time: '18:45' });
    const hourly = withFrequency(draft, 'hourly');
    expect(hourly).toMatchObject({ frequency: 'hourly', time: '00:45' });
    expect(withFrequency(hourly, 'daily')).toMatchObject({ frequency: 'daily', time: '09:00' });
    expect(withFrequency({ ...draft, time: '' }, 'hourly').time).toBe('00:00');
  });

  it('turns hourly minutes into the time the API takes', () => {
    expect(hourlyTime(0)).toBe('00:00');
    expect(hourlyTime(7)).toBe('00:07');
    expect(hourlyTime(45)).toBe('00:45');
    expect(minutesOf('00:45')).toBe(45);
  });

  it('offers every frequency, hourly first', () => {
    expect(FREQUENCY_CHOICES.map((choice) => choice.value)).toEqual([
      'hourly',
      'daily',
      'weekdays',
      'weekly',
      'monthly',
    ]);
  });
});

describe('what stops a schedule from being saved', () => {
  const draft = { ...emptyScheduleDraft(PARIS), run: { text: 'go', values: {} } };

  it('is nothing for a complete draft', () => {
    expect(scheduleProblem([], draft)).toBeNull();
    const named = { ...draft, run: { text: '', values: { topic: 'a', audience: 'b' } } };
    expect(scheduleProblem([TOPIC, AUDIENCE], named)).toBeNull();
  });

  it('asks for a time of day, or for minutes when hourly', () => {
    expect(scheduleProblem([], { ...draft, time: '' })).toBe('Choose a time of day.');
    expect(scheduleProblem([], { ...draft, frequency: 'hourly', time: '' })).toBe(
      'Enter the minutes past the hour, from 0 to 59.',
    );
  });

  it('asks for the text, or for each named value by its label', () => {
    expect(scheduleProblem([], { ...draft, run: { text: '  ', values: {} } })).toBe(
      'Say what each run should work on.',
    );
    const half = { ...draft, run: { text: '', values: { topic: 'bees' } } };
    expect(scheduleProblem([TOPIC, AUDIENCE], half)).toBe('Fill in audience.');
    expect(scheduleProblem([TOPIC, AUDIENCE], draft)).toBe('Fill in Topic, audience.');
  });
});

describe('the requests', () => {
  it('creates a schedule with the text of a pipeline without named inputs', () => {
    const draft = { ...emptyScheduleDraft(PARIS), run: { text: 'go', values: {} } };

    expect(toCreate(3, [], draft)).toEqual({
      pipeline_id: 3,
      frequency: 'weekly',
      time: '09:00',
      weekday: 0,
      timezone: PARIS,
      input: 'go',
    });
  });

  it('sends only the declared named values', () => {
    const run = { text: 'ignored', values: { topic: 'bees', audience: 'kids', stale: 'x' } };
    const draft = { ...emptyScheduleDraft(PARIS), frequency: 'daily' as const, run };

    expect(toCreate(3, [TOPIC, AUDIENCE], draft)).toEqual({
      pipeline_id: 3,
      frequency: 'daily',
      time: '09:00',
      timezone: PARIS,
      inputs: { topic: 'bees', audience: 'kids' },
    });
    expect(toPatch([TOPIC, AUDIENCE], draft)).toEqual({
      frequency: 'daily',
      time: '09:00',
      timezone: PARIS,
      inputs: { topic: 'bees', audience: 'kids' },
    });
  });
});
