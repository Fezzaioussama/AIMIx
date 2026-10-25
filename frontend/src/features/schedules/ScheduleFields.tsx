import { useMemo, type ReactNode } from 'react';

import { fieldClass } from '../settings/ProviderCard';
import {
  FREQUENCIES,
  FREQUENCY_CHOICES,
  WEEKDAY_NAMES,
  hourlyTime,
  minutesOf,
  ordinal,
  timeZoneOptions,
  withFrequency,
  type ScheduleDraft,
} from './scheduleDraft';

// `color-scheme: dark` gives the native time picker and option lists a dark look.
const controlClass = `${fieldClass} [color-scheme:dark] disabled:opacity-60`;
const MINUTES = Array.from({ length: 60 }, (_, minute) => minute);
const DAYS_OF_MONTH = Array.from({ length: 31 }, (_, index) => index + 1);
/** Past this day of the month, a shorter month runs on its last day instead. */
const LATE_DAY = 28;

interface FieldFrameProps {
  id: string;
  label: string;
  help?: string;
  children: ReactNode;
}

/** A label above its control, and an optional line of help below it. */
function FieldFrame({ id, label, help, children }: FieldFrameProps) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-300">
        {label}
      </label>
      {children}
      {help && (
        <p id={`${id}-help`} className="mt-1 text-xs text-slate-400">
          {help}
        </p>
      )}
    </div>
  );
}

/** What every timing field is given: its id, the draft, whether it is locked, and how to change it. */
interface FieldProps {
  id: string;
  draft: ScheduleDraft;
  disabled: boolean;
  onChange: (draft: ScheduleDraft) => void;
}

function FrequencyField({ id, draft, disabled, onChange }: FieldProps) {
  return (
    <FieldFrame id={id} label="Repeat">
      <select
        id={id}
        value={draft.frequency}
        disabled={disabled}
        onChange={(event) =>
          onChange(withFrequency(draft, event.target.value as ScheduleDraft['frequency']))
        }
        className={controlClass}
      >
        {FREQUENCY_CHOICES.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

function WeekdayField({ id, draft, disabled, onChange }: FieldProps) {
  return (
    <FieldFrame id={id} label="Day of the week">
      <select
        id={id}
        value={draft.weekday}
        disabled={disabled}
        onChange={(event) => onChange({ ...draft, weekday: Number(event.target.value) })}
        className={controlClass}
      >
        {WEEKDAY_NAMES.map((name, index) => (
          <option key={name} value={index}>
            {name}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

function DayOfMonthField({ id, draft, disabled, onChange }: FieldProps) {
  const late = draft.dayOfMonth > LATE_DAY;
  return (
    <FieldFrame
      id={id}
      label="Day of the month"
      help={late ? 'In a shorter month it runs on the last day.' : undefined}
    >
      <select
        id={id}
        value={draft.dayOfMonth}
        disabled={disabled}
        aria-describedby={late ? `${id}-help` : undefined}
        onChange={(event) => onChange({ ...draft, dayOfMonth: Number(event.target.value) })}
        className={controlClass}
      >
        {DAYS_OF_MONTH.map((day) => (
          <option key={day} value={day}>
            {ordinal(day)}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

/** The time of day, or, for an hourly schedule, the minutes past the hour. */
function ClockField({ id, draft, disabled, onChange }: FieldProps) {
  if (FREQUENCIES[draft.frequency].asks.clock === 'minutes') {
    return (
      <FieldFrame id={id} label="Minutes past the hour">
        <select
          id={id}
          value={minutesOf(draft.time)}
          disabled={disabled}
          onChange={(event) => onChange({ ...draft, time: hourlyTime(Number(event.target.value)) })}
          className={controlClass}
        >
          {MINUTES.map((minute) => (
            <option key={minute} value={minute}>
              {String(minute).padStart(2, '0')}
            </option>
          ))}
        </select>
      </FieldFrame>
    );
  }
  return (
    <FieldFrame id={id} label="Time">
      <input
        id={id}
        type="time"
        required
        value={draft.time}
        disabled={disabled}
        onChange={(event) => onChange({ ...draft, time: event.target.value })}
        className={controlClass}
      />
    </FieldFrame>
  );
}

function ZoneField({ id, draft, disabled, onChange }: FieldProps) {
  const zones = useMemo(() => timeZoneOptions(draft.timezone), [draft.timezone]);
  return (
    <FieldFrame
      id={id}
      label="Time zone"
      help="Starts as this device's time zone. Times follow its clock, summer time included."
    >
      <select
        id={id}
        value={draft.timezone}
        disabled={disabled}
        aria-describedby={`${id}-help`}
        onChange={(event) => onChange({ ...draft, timezone: event.target.value })}
        className={controlClass}
      >
        {zones.map((zone) => (
          <option key={zone} value={zone}>
            {zone}
          </option>
        ))}
      </select>
    </FieldFrame>
  );
}

interface ScheduleFieldsProps {
  /** Makes each field's id unique on the page. */
  idBase: string;
  draft: ScheduleDraft;
  disabled: boolean;
  onChange: (draft: ScheduleDraft) => void;
}

/** When a schedule runs: how often, the day it needs, the time, and the time zone. */
export function ScheduleFields({ idBase, draft, disabled, onChange }: ScheduleFieldsProps) {
  const { asks } = FREQUENCIES[draft.frequency];
  const shared = { draft, disabled, onChange };

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FrequencyField id={`${idBase}-frequency`} {...shared} />
      {asks.weekday && <WeekdayField id={`${idBase}-weekday`} {...shared} />}
      {asks.dayOfMonth && <DayOfMonthField id={`${idBase}-day`} {...shared} />}
      <ClockField id={`${idBase}-clock`} {...shared} />
      <ZoneField id={`${idBase}-zone`} {...shared} />
    </div>
  );
}
