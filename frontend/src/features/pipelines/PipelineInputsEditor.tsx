import type { PipelineInput } from '../../core/api/types';
import { addInput, inputNameProblem, toInputName } from './pipelineInputs';

const fieldClass =
  'w-full rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-sky-400';

interface PipelineInputsEditorProps {
  inputs: PipelineInput[];
  onChange: (inputs: PipelineInput[]) => void;
}

/** The named values every run is given, shared by the builder and the planner review. */
export function PipelineInputsEditor({ inputs, onChange }: PipelineInputsEditorProps) {
  function patch(index: number, change: Partial<PipelineInput>) {
    onChange(inputs.map((field, i) => (i === index ? { ...field, ...change } : field)));
  }

  return (
    <div className="space-y-2">
      {inputs.length === 0 && (
        <p className="text-xs text-slate-400">
          No named inputs: each run takes one free-text input as {'{input}'}.
        </p>
      )}
      {inputs.map((field, index) => (
        <InputFieldCard
          key={index}
          field={field}
          position={index + 1}
          problem={inputNameProblem(field.name, inputs)}
          onChange={(change) => patch(index, change)}
          onRemove={() => onChange(inputs.filter((_, i) => i !== index))}
        />
      ))}
      <button
        type="button"
        onClick={() => onChange(addInput(inputs))}
        className="w-full rounded-md border border-dashed border-white/20 px-3 py-1.5 text-xs text-slate-300 transition-colors hover:border-sky-400/40 hover:text-sky-300"
      >
        + Add input
      </button>
    </div>
  );
}

interface InputFieldCardProps {
  field: PipelineInput;
  position: number;
  problem: string | null;
  onChange: (change: Partial<PipelineInput>) => void;
  onRemove: () => void;
}

function InputFieldCard({ field, position, problem, onChange, onRemove }: InputFieldCardProps) {
  return (
    <div className="space-y-1.5 rounded-lg border border-white/10 bg-slate-900/40 p-2">
      <div className="flex items-center gap-1 font-mono text-xs text-sky-300">
        {'{'}
        <input
          type="text"
          value={field.name}
          aria-label={`Name of input ${position}`}
          aria-invalid={problem !== null}
          onChange={(event) => onChange({ name: toInputName(event.target.value) })}
          className={`${fieldClass} font-mono`}
        />
        {'}'}
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove input ${position}`}
          className="ml-1 font-sans text-lg leading-none text-slate-400 transition-colors hover:text-red-400"
        >
          &times;
        </button>
      </div>
      {problem && <p className="text-[11px] text-amber-300">{problem}</p>}
      <input
        type="text"
        value={field.label}
        placeholder="Label on the run form, e.g. Topic"
        aria-label={`Label of input ${position}`}
        onChange={(event) => onChange({ label: event.target.value })}
        className={fieldClass}
      />
      <input
        type="text"
        value={field.description}
        placeholder="What to enter, e.g. The subject of the posts"
        aria-label={`Description of input ${position}`}
        onChange={(event) => onChange({ description: event.target.value })}
        className={fieldClass}
      />
    </div>
  );
}
