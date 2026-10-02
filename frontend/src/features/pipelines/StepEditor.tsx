import type { AgentTool, PipelineStep } from '../../core/api/types';
import { StageInput } from './StageInput';
import { StepAgentFields } from './StepAgentFields';
import { StepRoleFields } from './StepRoleFields';
import { modelLabel } from './modelLabel';

interface StepEditorProps {
  steps: PipelineStep[];
  availableModels: string[];
  availableTools: AgentTool[];
  onChange: (index: number, patch: Partial<PipelineStep>) => void;
  onRemove: (index: number) => void;
}

export function StepEditor({
  steps,
  availableModels,
  availableTools,
  onChange,
  onRemove,
}: StepEditorProps) {
  return (
    <>
      {steps.map((step, index) => (
        <StepCard
          key={step.order}
          step={step}
          availableModels={availableModels}
          availableTools={availableTools}
          canRemove={steps.length > 1}
          onChange={(patch) => onChange(index, patch)}
          onRemove={() => onRemove(index)}
        />
      ))}
    </>
  );
}

interface StepCardProps {
  step: PipelineStep;
  availableModels: string[];
  availableTools: AgentTool[];
  canRemove: boolean;
  onChange: (patch: Partial<PipelineStep>) => void;
  onRemove: () => void;
}

function StepCard({
  step,
  availableModels,
  availableTools,
  canRemove,
  onChange,
  onRemove,
}: StepCardProps) {
  return (
    <div
      id={`step-editor-${step.order}`}
      className="mb-3 scroll-mt-4 rounded-lg border border-white/10 bg-slate-900/40 p-3"
    >
      <StepCardHeader step={step} canRemove={canRemove} onChange={onChange} onRemove={onRemove} />
      <StepRoleFields step={step} onChange={onChange} />
      <StepAgentFields step={step} tools={availableTools} onChange={onChange} />
      <StepCardFields step={step} availableModels={availableModels} onChange={onChange} />
    </div>
  );
}

function StepCardHeader({
  step,
  canRemove,
  onChange,
  onRemove,
}: Pick<StepCardProps, 'step' | 'canRemove' | 'onChange' | 'onRemove'>) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <span className="flex size-6 items-center justify-center rounded-full bg-sky-400/15 text-xs font-semibold text-sky-400">
        {step.order}
      </span>
      <StageInput
        value={step.stage}
        label={`Stage of step ${step.order}`}
        onChange={(stage) => onChange({ stage })}
      />
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove step ${step.order}`}
        disabled={!canRemove}
        className="text-lg leading-none text-slate-400 transition-colors hover:text-red-400"
      >
        &times;
      </button>
    </div>
  );
}

function StepCardFields({
  step,
  availableModels,
  onChange,
}: Pick<StepCardProps, 'step' | 'availableModels' | 'onChange'>) {
  return (
    <>
      <label className="mb-1 block text-xs text-slate-400">Model</label>
      <select
        value={step.model}
        onChange={(event) => onChange({ model: event.target.value })}
        className="mb-2 w-full rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-400"
      >
        {availableModels.map((model) => (
          <option key={model} value={model}>
            {modelLabel(model)}
          </option>
        ))}
      </select>
      <label className="mb-1 block text-xs text-slate-400">Prompt (use {'{input}'})</label>
      <textarea
        value={step.prompt}
        placeholder="Define instructions..."
        onChange={(event) => onChange({ prompt: event.target.value })}
        className="h-20 w-full resize-y rounded-md border border-white/10 bg-slate-900 p-2 text-xs text-slate-100 outline-none focus:border-sky-400"
      />
    </>
  );
}
