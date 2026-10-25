import type { PipelineInput } from '../../core/api/types';
import { REVIEW_FEEDBACK, STAGE_INPUT, unknownPlaceholders } from './pipelineInputs';

interface PromptPlaceholdersProps {
  prompt: string;
  inputs: PipelineInput[];
}

/** Under a step's prompt: the placeholders it can use, and any it uses that nothing fills. */
export function PromptPlaceholders({ prompt, inputs }: PromptPlaceholdersProps) {
  const unknown = unknownPlaceholders(prompt, inputs);
  return (
    <div className="mt-1 space-y-0.5 text-[11px] text-slate-400">
      <p className="flex flex-wrap items-baseline gap-x-1.5">
        <code className="text-sky-300/80">{`{${STAGE_INPUT}}`}</code>
        <span>previous stage’s result</span>
        <code className="text-sky-300/80">{`{${REVIEW_FEEDBACK}}`}</code>
        <span>a reviewer’s feedback when work is sent back</span>
        {inputs.map((field) => (
          <code key={field.name} className="text-sky-300/80">{`{${field.name}}`}</code>
        ))}
      </p>
      {unknown.length > 0 && (
        <p className="text-amber-300">
          Not an input, left as written: {unknown.map((name) => `{${name}}`).join(', ')}
        </p>
      )}
    </div>
  );
}
