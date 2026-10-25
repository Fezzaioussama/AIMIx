interface ToggleSwitchProps {
  checked: boolean;
  /** What the switch does, as its accessible name: "Let agents use crm". */
  label: string;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}

/** An on/off switch with its state in words beside it ("On" / "Off"). */
export function ToggleSwitch({ checked, label, disabled = false, onChange }: ToggleSwitchProps) {
  return (
    <div className="flex shrink-0 items-center gap-2">
      <span aria-hidden="true" className="text-xs text-slate-300">
        {checked ? 'On' : 'Off'}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60 ${
          checked ? 'border-sky-400/60 bg-sky-500/70' : 'border-white/15 bg-slate-700/70'
        }`}
      >
        <span
          aria-hidden="true"
          className={`inline-block size-4 rounded-full bg-white shadow motion-safe:transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  );
}
