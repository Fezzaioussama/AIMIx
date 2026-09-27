import type { Pipeline, PipelineStep } from '../../core/api/types';
import { modelLabel } from './modelLabel';

interface GeneratedStepsProps {
  pipeline: Pipeline;
  availableModels: string[];
  onChange: (index: number, patch: Partial<PipelineStep>) => void;
}

export function GeneratedSteps({ pipeline, availableModels, onChange }: GeneratedStepsProps) {
  return (
    <div>
      {pipeline.steps.map((step, index) => (
        <div key={index}>
          <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
            <div className="mb-4 flex items-center gap-3">
              <span className="flex size-7 items-center justify-center rounded-full bg-sky-400/15 text-sm font-semibold text-sky-400">
                {step.order}
              </span>
              <span className="font-semibold text-slate-200">Step {step.order}</span>
            </div>

            <label className="mb-1 block text-xs text-slate-400">Prompt Template:</label>
            <textarea
              value={step.prompt}
              onChange={(event) => onChange(index, { prompt: event.target.value })}
              className="mb-4 h-24 w-full resize-y rounded-lg border border-white/10 bg-slate-900 p-3 text-sm text-slate-100 outline-none focus:border-sky-400"
            />

            <label className="mb-1 block text-xs text-slate-400">Model:</label>
            <select
              value={step.model}
              onChange={(event) => onChange(index, { model: event.target.value })}
              className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400"
            >
              {availableModels.map((model) => (
                <option key={model} value={model}>
                  {modelLabel(model)}
                </option>
              ))}
            </select>
          </div>

          {index < pipeline.steps.length - 1 && (
            <div className="py-2 text-center text-xl text-slate-500" aria-hidden="true">
              ↓
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
