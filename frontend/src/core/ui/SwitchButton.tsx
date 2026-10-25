interface SwitchButtonProps {
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
  /** The accessible name, when no visible text names the switch. */
  label?: string;
  /** The id of the visible text that names the switch. */
  labelledBy?: string;
  /** The id of the text that explains what the current setting means. */
  describedBy?: string;
}

/** An on/off switch with the keyboard and screen-reader behaviour of `role="switch"`. */
export function SwitchButton({
  checked,
  disabled,
  onChange,
  label,
  labelledBy,
  describedBy,
}: SwitchButtonProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-60 ${
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
  );
}
