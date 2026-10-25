import type {
  PipelineInput,
  Schedule,
  ScheduleFrequency,
  ScheduleInput,
  SchedulePatch,
  ScheduleTiming,
} from '../../core/api/types';
import {
  EMPTY_RUN_DRAFT,
  inputLabel,
  isRunReady,
  runRequest,
  type RunDraft,
} from '../pipelines/pipelineInputs';

/**
 * What the schedule form holds, and the plain-language side of schedules: how a timing is
 * said in words, and how a draft becomes a request. When a schedule runs is decided by the
 * server (`api/services/schedules/timing.py`); nothing here works out a time.
 */
export const DEFAULT_TIME = '09:00';
/** "HH:MM" on a 24-hour clock, as the time field gives it and the API takes it. */
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
/** Monday first, as the API counts days of the week (0 is Monday). */
export const WEEKDAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;
/** Past this day, a month may be too short for it, so the last day is used there. */
const SHORTEST_MONTH_DAYS = 28;

export interface ScheduleDraft {
  frequency: ScheduleFrequency;
  /** "HH:MM"; an hourly schedule uses the minutes only. */
  time: string;
  /** 0 is Monday. */
  weekday: number;
  dayOfMonth: number;
  /** An IANA time zone name. */
  timezone: string;
  /** What each run is given: free text, or a value per named input. */
  run: RunDraft;
}

/** What one frequency asks of the form, and how it reads in words (Strategy + Registry). */
interface FrequencyRule {
  /** The choice in the form's list. */
  label: string;
  /** Which fields the form shows: a time of day, or minutes past the hour; a day. */
  asks: { clock: 'time' | 'minutes'; weekday: boolean; dayOfMonth: boolean };
  /** The schedule in words, up to and including its time. */
  words: (timing: ScheduleTiming) => string;
  /** A note on a day that some months lack. */
  note?: (timing: ScheduleTiming) => string;
}

/** 1 as "1st", 12 as "12th", 23 as "23rd". */
export function ordinal(day: number): string {
  const teens = day % 100 >= 11 && day % 100 <= 13;
  const suffix = teens ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[day % 10];
  return `${day}${suffix ?? 'th'}`;
}

/** The minutes of an "HH:MM" time. */
export function minutesOf(time: string): number {
  return Number(time.slice(3, 5));
}

/** An hourly schedule's minutes past the hour as the "HH:MM" the API takes. */
export function hourlyTime(minutes: number): string {
  return `00:${String(minutes).padStart(2, '0')}`;
}

function hourlyWords(timing: ScheduleTiming): string {
  const minutes = minutesOf(timing.time);
  if (minutes === 0) return 'Every hour, on the hour';
  return `Every hour, ${minutes} ${minutes === 1 ? 'minute' : 'minutes'} past`;
}

function lastDayNote(timing: ScheduleTiming): string {
  const day = timing.day_of_month ?? 1;
  return day > SHORTEST_MONTH_DAYS ? 'or the last day, in shorter months' : '';
}

export const FREQUENCIES: Record<ScheduleFrequency, FrequencyRule> = {
  hourly: {
    label: 'Every hour',
    asks: { clock: 'minutes', weekday: false, dayOfMonth: false },
    words: hourlyWords,
  },
  daily: {
    label: 'Every day',
    asks: { clock: 'time', weekday: false, dayOfMonth: false },
    words: (timing) => `Every day at ${timing.time}`,
  },
  weekdays: {
    label: 'Every weekday (Monday to Friday)',
    asks: { clock: 'time', weekday: false, dayOfMonth: false },
    words: (timing) => `Every weekday at ${timing.time}`,
  },
  weekly: {
    label: 'Every week',
    asks: { clock: 'time', weekday: true, dayOfMonth: false },
    words: (timing) => `Every ${WEEKDAY_NAMES[timing.weekday ?? 0]} at ${timing.time}`,
  },
  monthly: {
    label: 'Every month',
    asks: { clock: 'time', weekday: false, dayOfMonth: true },
    words: (timing) =>
      `On the ${ordinal(timing.day_of_month ?? 1)} of every month at ${timing.time}`,
    note: lastDayNote,
  },
};

export const FREQUENCY_CHOICES = (Object.keys(FREQUENCIES) as ScheduleFrequency[]).map((value) => ({
  value,
  label: FREQUENCIES[value].label,
}));

/** "Europe/Paris" as "Paris time", "America/New_York" as "New York time"; UTC stays UTC. */
export function timeZoneName(zone: string): string {
  if (zone === 'UTC' || zone === 'Etc/UTC') return 'UTC';
  const city = zone.split('/').pop() ?? zone;
  return `${city.replace(/_/g, ' ')} time`;
}

/** A timing in words: "Every Monday at 09:00, Paris time". */
export function describeTiming(timing: ScheduleTiming): string {
  const rule = FREQUENCIES[timing.frequency];
  // An hourly schedule's minutes are the same on every clock, so it names no zone.
  const zone = rule.asks.clock === 'time' ? `, ${timeZoneName(timing.timezone)}` : '';
  const note = rule.note?.(timing);
  return `${rule.words(timing)}${zone}${note ? ` (${note})` : ''}`;
}

/** "Mon 26 Oct, 09:00" on the clock of `timezone`, the one the schedule is written in. */
export function formatNextRun(iso: string, timezone: string): string {
  const options: Intl.DateTimeFormatOptions = {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  };
  try {
    return clock(iso, { ...options, timeZone: timezone });
  } catch {
    // A zone the server knows and this browser does not.
    return `${clock(iso, { ...options, timeZone: 'UTC' })} UTC`;
  }
}

function clock(iso: string, options: Intl.DateTimeFormatOptions): string {
  const parts = new Intl.DateTimeFormat('en-GB', options).formatToParts(new Date(iso));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((candidate) => candidate.type === type)?.value ?? '';
  return `${part('weekday')} ${part('day')} ${part('month')}, ${part('hour')}:${part('minute')}`;
}

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
}

/** UTC first, then every zone the browser knows, and `current` even if it does not. */
export function timeZoneOptions(current: string): string[] {
  const known =
    typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : [];
  const others = [...new Set([current, ...known])].filter((zone) => zone !== 'UTC');
  return ['UTC', ...others.sort()];
}

/** A new schedule: every Monday at 09:00 on the browser's clock. */
export function emptyScheduleDraft(timezone: string = browserTimeZone()): ScheduleDraft {
  return {
    frequency: 'weekly',
    time: DEFAULT_TIME,
    weekday: 0,
    dayOfMonth: 1,
    timezone,
    run: EMPTY_RUN_DRAFT,
  };
}

export function draftFromSchedule(schedule: Schedule): ScheduleDraft {
  return {
    frequency: schedule.frequency,
    time: schedule.time,
    weekday: schedule.weekday ?? 0,
    dayOfMonth: schedule.day_of_month ?? 1,
    timezone: schedule.timezone,
    run: { text: schedule.input, values: { ...schedule.inputs } },
  };
}

/** The timing a draft says, with only the day field its frequency uses. */
export function timingOf(draft: ScheduleDraft): ScheduleTiming {
  const { weekday, dayOfMonth } = FREQUENCIES[draft.frequency].asks;
  return {
    frequency: draft.frequency,
    time: draft.time,
    ...(weekday ? { weekday: draft.weekday } : {}),
    ...(dayOfMonth ? { day_of_month: draft.dayOfMonth } : {}),
    timezone: draft.timezone,
  };
}

export function isTimeValid(time: string): boolean {
  return TIME_PATTERN.test(time);
}

/**
 * The draft with another frequency. Hourly asks for minutes past the hour instead of a time
 * of day, so crossing that line keeps the minutes one way and starts from the default time
 * the other.
 */
export function withFrequency(draft: ScheduleDraft, frequency: ScheduleFrequency): ScheduleDraft {
  const before = FREQUENCIES[draft.frequency].asks.clock;
  const after = FREQUENCIES[frequency].asks.clock;
  if (before === after) return { ...draft, frequency };
  const minutes = isTimeValid(draft.time) ? minutesOf(draft.time) : 0;
  return { ...draft, frequency, time: after === 'minutes' ? hourlyTime(minutes) : DEFAULT_TIME };
}

/** What stops a draft from being saved, in words, or null when it can be. */
export function scheduleProblem(inputs: PipelineInput[], draft: ScheduleDraft): string | null {
  if (!isTimeValid(draft.time)) {
    return FREQUENCIES[draft.frequency].asks.clock === 'minutes'
      ? 'Enter the minutes past the hour, from 0 to 59.'
      : 'Choose a time of day.';
  }
  if (isRunReady(inputs, draft.run)) return null;
  if (inputs.length === 0) return 'Say what each run should work on.';
  const missing = inputs.filter((field) => !(draft.run.values[field.name] ?? '').trim());
  return `Fill in ${missing.map(inputLabel).join(', ')}.`;
}

/** The body that creates a schedule of a saved pipeline. */
export function toCreate(
  pipelineId: number,
  inputs: PipelineInput[],
  draft: ScheduleDraft,
): ScheduleInput {
  return { pipeline_id: pipelineId, ...timingOf(draft), ...runRequest(inputs, draft.run) };
}

/** The body that saves an edit: the whole timing and the run inputs, as the form holds them. */
export function toPatch(inputs: PipelineInput[], draft: ScheduleDraft): SchedulePatch {
  return { ...timingOf(draft), ...runRequest(inputs, draft.run) };
}
