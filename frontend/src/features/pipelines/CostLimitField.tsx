import { useId } from 'react';

interface CostLimitFieldProps {
  /** The amount as typed; empty means no limit. */
  value: string;
  disabled: boolean;
  /** Why the typed amount cannot be used, or null. */
  problem: string | null;
  onChange: (value: string) => void;
}

/** The run form's optional "Stop if it costs more than $…" field. */
export function CostLimitField({ value, disabled, problem, onChange }: CostLimitFieldProps) {
  const id = useId();
  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-200">
        Stop if it costs more than <span className="font-normal text-slate-400">(optional)</span>
      </label>
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="text-slate-300">
          $
        </span>
        <input
          id={id}
          type="text"
          inputMode="decimal"
          value={value}
          disabled={disabled}
          placeholder="e.g. 0.50"
          aria-invalid={problem !== null}
          aria-describedby={`${id}-note`}
          onChange={(event) => onChange(event.target.value)}
          className="w-32 rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm tabular-nums transition-[border-color,box-shadow] outline-none focus:border-sky-400/60 focus:shadow-[0_0_0_4px_rgba(56,189,248,0.1)] focus-visible:outline-2 focus-visible:outline-sky-400"
        />
      </div>
      <p
        id={`${id}-note`}
        aria-live="polite"
        className={`mt-1.5 text-xs ${problem ? 'text-amber-300' : 'text-slate-400'}`}
      >
        {problem ?? 'The run stops by itself once the model calls cost this much.'}
      </p>
    </div>
  );
}
