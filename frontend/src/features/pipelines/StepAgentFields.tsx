import type { AgentTool, PipelineStep } from '../../core/api/types';

interface StepAgentFieldsProps {
  step: PipelineStep;
  tools: AgentTool[];
  onChange: (patch: Partial<PipelineStep>) => void;
}

/** Agent identity and capabilities shared by manual and generated step editors. */
export function StepAgentFields({ step, tools, onChange }: StepAgentFieldsProps) {
  return (
    <div className="mb-3 space-y-3">
      <AgentRoleField step={step} onChange={onChange} />
      <ToolPolicyField
        allowedTools={step.allowed_tools}
        tools={tools}
        onChange={(allowed_tools) => onChange({ allowed_tools })}
      />
    </div>
  );
}

function AgentRoleField({ step, onChange }: Pick<StepAgentFieldsProps, 'step' | 'onChange'>) {
  return (
    <div>
      <label htmlFor={`agent-role-${step.order}`} className="mb-1 block text-xs text-slate-400">
        Agent role
      </label>
      <input
        id={`agent-role-${step.order}`}
        type="text"
        value={step.role}
        placeholder="e.g. Researcher, reviewer, writer"
        onChange={(event) => onChange({ role: event.target.value })}
        className="w-full rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-400"
      />
    </div>
  );
}

interface ToolPolicyFieldProps {
  allowedTools: string[] | null;
  tools: AgentTool[];
  onChange: (names: string[] | null) => void;
}

function ToolPolicyField({ allowedTools, tools, onChange }: ToolPolicyFieldProps) {
  const unavailable = (allowedTools ?? [])
    .filter((name) => !tools.some((tool) => tool.name === name))
    .map((name) => ({ name, source: 'Unavailable', description: 'Not in the current catalog' }));
  const visibleTools = [...tools, ...unavailable];
  const summary =
    allowedTools === null ? 'All configured tools' : `${allowedTools.length} selected`;

  return (
    <div>
      <p className="mb-1 text-xs text-slate-400">Allowed tools</p>
      <div className="mb-2 flex gap-2">
        <PolicyButton active={allowedTools === null} onClick={() => onChange(null)}>
          All tools
        </PolicyButton>
        <PolicyButton active={allowedTools?.length === 0} onClick={() => onChange([])}>
          No tools
        </PolicyButton>
      </div>
      <details className="rounded-md border border-white/10 bg-slate-900/50 px-2 py-1.5 text-xs">
        <summary className="cursor-pointer text-slate-300">Choose tools · {summary}</summary>
        <ToolChecklist tools={visibleTools} allowedTools={allowedTools} onChange={onChange} />
      </details>
    </div>
  );
}

function ToolChecklist({ tools, allowedTools, onChange }: ToolPolicyFieldProps) {
  if (tools.length === 0) {
    return <p className="mt-2 text-slate-400">No tools are currently available.</p>;
  }
  return (
    <div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
      {tools.map((tool) => (
        <label
          key={tool.name}
          className="flex cursor-pointer items-start gap-2 rounded px-1 py-1 hover:bg-white/5"
        >
          <input
            type="checkbox"
            checked={allowedTools === null || allowedTools.includes(tool.name)}
            onChange={(event) =>
              onChange(toggleTool(allowedTools, tools, tool.name, event.target.checked))
            }
            className="mt-0.5 accent-sky-400"
          />
          <span className="min-w-0 text-slate-200">
            <span className="font-medium">{tool.name}</span>
            <span className="ml-1 text-slate-500">· {tool.source}</span>
            {tool.description && <span className="block text-slate-400">{tool.description}</span>}
          </span>
        </label>
      ))}
    </div>
  );
}

function toggleTool(
  selected: string[] | null,
  tools: AgentTool[],
  name: string,
  checked: boolean,
): string[] {
  const current = selected ?? tools.map((tool) => tool.name);
  return checked ? [...new Set([...current, name])] : current.filter((entry) => entry !== name);
}

interface PolicyButtonProps {
  active: boolean;
  onClick: () => void;
  children: string;
}

function PolicyButton({ active, onClick, children }: PolicyButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-md border px-2 py-1 text-xs ${
        active
          ? 'border-sky-400/50 bg-sky-400/15 text-sky-300'
          : 'border-white/10 text-slate-300 hover:bg-white/10'
      }`}
    >
      {children}
    </button>
  );
}
