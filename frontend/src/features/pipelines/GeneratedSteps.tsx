import type { Pipeline, PipelineStep } from '../../core/api/types';
import { StageArrow } from './StageArrow';
import { StageHeader } from './StageHeader';
import { StageInput } from './StageInput';
import { StepRoleFields } from './StepRoleFields';
import { modelLabel } from './modelLabel';
import { groupByStage, stepLabel } from './stages';

interface GeneratedStepsProps {
  pipeline: Pipeline;
  availableModels: string[];
  onChange: (index: number, patch: Partial<PipelineStep>) => void;
  onRemove: (index: number) => void;
}

/** The planned pipeline, drawn stage by stage; parallel steps sit side by side. */
export function GeneratedSteps({
  pipeline, availableModels, onChange, onRemove,
}: GeneratedStepsProps) {
  // Keep each step's position in the pipeline so edits patch the right one.
  const indexed = pipeline.steps.map((step, index) => ({ step, index }));
  const stages = groupByStage(indexed, ({ step }) => step.stage);

  return (
    <div>
      {stages.map((group, position) => (
        <div key={group.stage}>
          <StageHeader stage={group.stage} stepCount={group.items.length} />
          <div className={group.items.length > 1 ? 'grid gap-4 md:grid-cols-2' : ''}>
            {group.items.map(({ step, index }) => (
              <GeneratedStep
                key={index}
                step={step}
                availableModels={availableModels}
                onChange={(patch) => onChange(index, patch)}
                onRemove={() => onRemove(index)}
                canRemove={pipeline.steps.length > 1}
              />
            ))}
          </div>
          {position < stages.length - 1 && <StageArrow />}
        </div>
      ))}
    </div>
  );
}

interface GeneratedStepProps {
  step: PipelineStep;
  availableModels: string[];
  onChange: (patch: Partial<PipelineStep>) => void;
  onRemove: () => void;
  canRemove: boolean;
}

function GeneratedStep({ step, availableModels, onChange, onRemove, canRemove }: GeneratedStepProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-900/40 p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex size-7 items-center justify-center rounded-full bg-sky-400/15 text-sm font-semibold text-sky-400">
            {step.order}
          </span>
          <span className="font-semibold text-slate-200">{stepLabel(step)}</span>
        </div>
        <div className="flex items-center gap-3">
          <StageInput
            value={step.stage}
            label={`Stage of step ${step.order}`}
            onChange={(stage) => onChange({ stage })}
          />
          {canRemove && (
            <button type="button" onClick={onRemove} aria-label={`Remove step ${step.order}`} className="text-lg leading-none text-slate-400 hover:text-red-400">
              &times;
            </button>
          )}
        </div>
      </div>

      <StepRoleFields step={step} onChange={onChange} />

      <label className="mb-1 block text-xs text-slate-400">Prompt Template:</label>
      <textarea
        value={step.prompt}
        placeholder="Describe this result using {input}"
        onChange={(event) => onChange({ prompt: event.target.value })}
        className="mb-4 h-24 w-full resize-y rounded-lg border border-white/10 bg-slate-900 p-3 text-sm text-slate-100 outline-none focus:border-sky-400"
      />

      <label className="mb-1 block text-xs text-slate-400">Model:</label>
      <select
        value={step.model}
        onChange={(event) => onChange({ model: event.target.value })}
        className="w-full rounded-lg border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-400"
      >
        {availableModels.map((model) => (
          <option key={model} value={model}>
            {modelLabel(model)}
          </option>
        ))}
      </select>
    </div>
  );
}
