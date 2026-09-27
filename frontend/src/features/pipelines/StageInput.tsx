interface StageInputProps {
  value: number;
  onChange: (stage: number) => void;
  label: string;
}

/** Stage picker. Giving several steps the same stage makes them run in parallel. */
export function StageInput({ value, onChange, label }: StageInputProps) {
  return (
    <label className="flex items-center gap-2 text-xs text-slate-400">
      Stage
      <input
        type="number"
        min={1}
        value={value}
        aria-label={label}
        title="Steps with the same stage run in parallel"
        onChange={(event) => onChange(Math.max(1, Number(event.target.value) || 1))}
        className="w-14 rounded-md border border-white/10 bg-slate-900 px-2 py-1 text-xs text-slate-100 outline-none focus:border-sky-400"
      />
    </label>
  );
}
