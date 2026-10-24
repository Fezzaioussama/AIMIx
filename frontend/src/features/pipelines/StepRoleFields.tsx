import type { PipelineStep } from '../../core/api/types';

interface StepRoleFieldsProps {
  step: PipelineStep;
  onChange: (patch: Partial<PipelineStep>) => void;
}

/**
 * A step's title, whether its result is an output or intermediate work, and
 * the expected output its agent must deliver.
 */
export function StepRoleFields({ step, onChange }: StepRoleFieldsProps) {
  return (
    <div className="mb-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={step.title}
          placeholder={`Title (e.g. "Tweet draft")`}
          aria-label={`Title of step ${step.order}`}
          onChange={(event) => onChange({ title: event.target.value })}
          className="min-w-0 flex-1 rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-400"
        />
        <div className="flex rounded-md border border-white/10 p-0.5 text-xs" role="group">
          <RoleButton active={!step.is_output} onClick={() => onChange({ is_output: false })}>
            Intermediate
          </RoleButton>
          <RoleButton active={step.is_output} onClick={() => onChange({ is_output: true })}>
            Output
          </RoleButton>
        </div>
      </div>
      <textarea
        rows={2}
        value={step.expected_output}
        placeholder="Expected output, e.g. One tweet under 280 characters with two hashtags"
        aria-label={`Expected output of step ${step.order}`}
        onChange={(event) => onChange({ expected_output: event.target.value })}
        className="w-full resize-y rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-400"
      />
    </div>
  );
}

interface RoleButtonProps {
  active: boolean;
  onClick: () => void;
  children: string;
}

function RoleButton({ active, onClick, children }: RoleButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded px-2 py-1 transition-colors ${
        active ? 'bg-amber-400/20 text-amber-200' : 'text-slate-400 hover:text-slate-200'
      }`}
    >
      {children}
    </button>
  );
}
