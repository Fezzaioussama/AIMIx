import type { PipelineStep } from '../../core/api/types';
import { StageInput } from './StageInput';
import { StepRoleFields } from './StepRoleFields';
import { modelLabel } from './modelLabel';

interface StepEditorProps {
  steps: PipelineStep[];
  availableModels: string[];
  onChange: (index: number, patch: Partial<PipelineStep>) => void;
  onRemove: (index: number) => void;
}

export function StepEditor({ steps, availableModels, onChange, onRemove }: StepEditorProps) {
  return (
    <>
      {steps.map((step, index) => (
        <div id={`step-editor-${step.order}`} key={step.order} className="mb-3 scroll-mt-4 rounded-lg border border-white/10 bg-slate-900/40 p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="flex size-6 items-center justify-center rounded-full bg-sky-400/15 text-xs font-semibold text-sky-400">
              {step.order}
            </span>
            <StageInput
              value={step.stage}
              label={`Stage of step ${step.order}`}
              onChange={(stage) => onChange(index, { stage })}
            />
            <button
              type="button"
              onClick={() => onRemove(index)}
              aria-label={`Remove step ${step.order}`}
              disabled={steps.length === 1}
              className="text-lg leading-none text-slate-400 transition-colors hover:text-red-400"
            >
              &times;
            </button>
          </div>
          <StepRoleFields step={step} onChange={(patch) => onChange(index, patch)} />
          <label className="mb-1 block text-xs text-slate-400">Model</label>
          <select
            value={step.model}
            onChange={(event) => onChange(index, { model: event.target.value })}
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
            onChange={(event) => onChange(index, { prompt: event.target.value })}
            className="h-20 w-full resize-y rounded-md border border-white/10 bg-slate-900 p-2 text-xs text-slate-100 outline-none focus:border-sky-400"
          />
        </div>
      ))}
    </>
  );
}
