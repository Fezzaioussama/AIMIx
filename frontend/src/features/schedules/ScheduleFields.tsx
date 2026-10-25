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

interface FieldProps {
  id: string;
  label: string;
  help?: string;
  children: ReactNode;
}

function Field({ id, label, help, children }: FieldProps) {
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
  const patch = (change: Partial<ScheduleDraft>) => onChange({ ...draft, ...change });
  const zones = useMemo(() => timeZoneOptions(draft.timezone), [draft.timezone]);

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field id={`${idBase}-frequency`} label="Repeat">
        <select
          id={`${idBase}-frequency`}
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
      </Field>
      {asks.weekday && (
        <Field id={`${idBase}-weekday`} label="Day of the week">
          <select
            id={`${idBase}-weekday`}
            value={draft.weekday}
            disabled={disabled}
            onChange={(event) => patch({ weekday: Number(event.target.value) })}
            className={controlClass}
          >
            {WEEKDAY_NAMES.map((name, index) => (
              <option key={name} value={index}>
                {name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {asks.dayOfMonth && (
        <Field
          id={`${idBase}-day`}
          label="Day of the month"
          help={draft.dayOfMonth > 28 ? 'In a shorter month it runs on the last day.' : undefined}
        >
          <select
            id={`${idBase}-day`}
            value={draft.dayOfMonth}
            disabled={disabled}
            aria-describedby={draft.dayOfMonth > 28 ? `${idBase}-day-help` : undefined}
            onChange={(event) => patch({ dayOfMonth: Number(event.target.value) })}
            className={controlClass}
          >
            {DAYS_OF_MONTH.map((day) => (
              <option key={day} value={day}>
                {ordinal(day)}
              </option>
            ))}
          </select>
        </Field>
      )}
      {asks.clock === 'time' ? (
        <Field id={`${idBase}-time`} label="Time">
          <input
            id={`${idBase}-time`}
            type="time"
            required
            value={draft.time}
            disabled={disabled}
            onChange={(event) => patch({ time: event.target.value })}
            className={controlClass}
          />
        </Field>
      ) : (
        <Field id={`${idBase}-minutes`} label="Minutes past the hour">
          <select
            id={`${idBase}-minutes`}
            value={minutesOf(draft.time)}
            disabled={disabled}
            onChange={(event) => patch({ time: hourlyTime(Number(event.target.value)) })}
            className={controlClass}
          >
            {MINUTES.map((minute) => (
              <option key={minute} value={minute}>
                {String(minute).padStart(2, '0')}
              </option>
            ))}
          </select>
        </Field>
      )}
      <Field
        id={`${idBase}-zone`}
        label="Time zone"
        help="Starts as this device's time zone. Times follow its clock, summer time included."
      >
        <select
          id={`${idBase}-zone`}
          value={draft.timezone}
          disabled={disabled}
          aria-describedby={`${idBase}-zone-help`}
          onChange={(event) => patch({ timezone: event.target.value })}
          className={controlClass}
        >
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}
