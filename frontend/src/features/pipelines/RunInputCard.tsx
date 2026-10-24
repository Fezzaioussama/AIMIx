import type { PipelineInput } from '../../core/api/types';
import { GlowButton } from '../../core/ui/GlowButton';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { inputLabel, isRunReady, type RunDraft } from './pipelineInputs';

const fieldClass =
  'w-full resize-y rounded-xl border border-white/10 bg-slate-950/60 p-4 text-sm transition-[border-color,box-shadow] outline-none focus:border-sky-400/60 focus:shadow-[0_0_0_4px_rgba(56,189,248,0.1)]';

interface RunInputCardProps {
  /** The saved pipeline's named inputs; none means one free-text input. */
  inputs: PipelineInput[];
  draft: RunDraft;
  isRunning: boolean;
  /** Unsaved edits: the server runs the stored version, so running waits for a save. */
  dirty: boolean;
  /** The pipeline exists on the server — only then is "save to run" the fix to suggest. */
  isSaved: boolean;
  message: string;
  onDraftChange: (draft: RunDraft) => void;
  onRun: () => void;
}

/** The builder's "Run Execution" panel: the run's inputs and the run button. */
export function RunInputCard({
  inputs,
  draft,
  isRunning,
  dirty,
  isSaved,
  message,
  onDraftChange,
  onRun,
}: RunInputCardProps) {
  return (
    <SpotlightCard className="mt-8 p-8">
      <h2 className="mb-4 text-xl font-semibold">Run Execution</h2>
      {inputs.length === 0 ? (
        <textarea
          value={draft.text}
          disabled={isRunning}
          aria-label="Run input"
          placeholder="Enter your initial input here..."
          onChange={(event) => onDraftChange({ ...draft, text: event.target.value })}
          className={`mb-4 h-28 ${fieldClass}`}
        />
      ) : (
        <NamedInputFields
          inputs={inputs}
          draft={draft}
          disabled={isRunning}
          onDraftChange={onDraftChange}
        />
      )}
      <GlowButton
        size="lg"
        onClick={onRun}
        busy={isRunning}
        disabled={!isRunReady(inputs, draft) || dirty}
      >
        {isRunning ? 'Executing…' : 'Run Pipeline'}
      </GlowButton>
      {dirty && isSaved && (
        <p className="mt-3 text-xs text-sky-300">Save your changes to run this version.</p>
      )}
      {message && <p className="mt-4 text-sm text-amber-300">{message}</p>}
    </SpotlightCard>
  );
}

interface NamedInputFieldsProps {
  inputs: PipelineInput[];
  draft: RunDraft;
  disabled: boolean;
  onDraftChange: (draft: RunDraft) => void;
}

/** One labelled field per declared input; every one must be filled to run. */
function NamedInputFields({ inputs, draft, disabled, onDraftChange }: NamedInputFieldsProps) {
  return (
    <div className="mb-4 grid gap-4 md:grid-cols-2">
      {inputs.map((field) => (
        <label key={field.name} className="block">
          <span className="mb-1.5 flex items-baseline gap-2 text-sm font-medium text-slate-200">
            {inputLabel(field)}
            <code className="text-xs font-normal text-sky-300/80">{`{${field.name}}`}</code>
          </span>
          <textarea
            value={draft.values[field.name] ?? ''}
            disabled={disabled}
            placeholder={field.description || 'Value for this input'}
            onChange={(event) =>
              onDraftChange({
                ...draft,
                values: { ...draft.values, [field.name]: event.target.value },
              })
            }
            className={`h-20 ${fieldClass}`}
          />
        </label>
      ))}
    </div>
  );
}
