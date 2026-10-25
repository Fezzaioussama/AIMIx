import { SwitchButton } from './SwitchButton';

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
      <SwitchButton checked={checked} disabled={disabled} onChange={onChange} label={label} />
    </div>
  );
}
