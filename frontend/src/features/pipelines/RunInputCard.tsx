import { useId } from 'react';

import { DOCUMENTS_INPUT_NAME } from '../../core/api/pipelines';
import type { PipelineInput } from '../../core/api/types';
import { GlowButton } from '../../core/ui/GlowButton';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { AttachDocument } from './AttachDocument';
import { CostLimitField } from './CostLimitField';
import {
  costLimitProblem,
  inputLabel,
  isRunReady,
  runInputLimitProblem,
  runInputSize,
  waitingForDocument,
  type RunDraft,
} from './pipelineInputs';
import { useInputReadings, type ReadingReport } from './useInputReadings';

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
  /** A document being read elsewhere for this run (the mission's message box), if any. */
  waitingFor?: string;
}

/**
 * The builder's "Run Execution" panel: the run's inputs and the run button, which waits
 * while a document for the run is still being read.
 */
export function RunInputCard({
  inputs,
  draft,
  isRunning,
  dirty,
  isSaved,
  message,
  onDraftChange,
  onRun,
  waitingFor = '',
}: RunInputCardProps) {
  const readings = useInputReadings();
  const waiting = readings.reading || waitingFor;
  return (
    <SpotlightCard className="mt-8 p-8">
      <h2 className="mb-4 text-xl font-semibold">Run Execution</h2>
      <RunInputFields
        inputs={inputs}
        draft={draft}
        disabled={isRunning}
        onDraftChange={onDraftChange}
        onReading={readings.report}
      />
      <CostLimitField
        value={draft.maxCost ?? ''}
        disabled={isRunning}
        problem={costLimitProblem(draft)}
        onChange={(maxCost) => onDraftChange({ ...draft, maxCost })}
      />
      <GlowButton
        size="lg"
        onClick={onRun}
        busy={isRunning}
        disabled={!isRunReady(inputs, draft) || dirty || waiting !== ''}
      >
        {isRunning ? 'Executing…' : 'Run Pipeline'}
      </GlowButton>
      {waiting && <p className="mt-3 text-xs text-sky-300">{waitingForDocument(waiting)}</p>}
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
  /** Told what each input is reading, by its name ('' for the free text). */
  onReading?: ReadingReport;
}

/**
 * What a run is given: one free-text field (with "Attach a document" and "Add a web page")
 * for a pipeline without named inputs, else one labelled field per input, and why the run
 * cannot take them when they are too long. The schedule form asks the same way.
 */
export function RunInputFields({
  inputs,
  draft,
  disabled,
  onDraftChange,
  onReading,
  label = 'Run input',
}: NamedInputFieldsProps & {
  /** The free-text field's accessible name, for a page that holds more than one run form. */
  label?: string;
}) {
  // Polite rather than an alert: the count changes with every key while the text is cut.
  const tooLong = runInputLimitProblem(inputs, draft);
  return (
    <>
      {inputs.length > 0 ? (
        <NamedInputFields
          inputs={inputs}
          draft={draft}
          disabled={disabled}
          onDraftChange={onDraftChange}
          onReading={onReading}
        />
      ) : (
        <div className="mb-4">
          <textarea
            value={draft.text}
            disabled={disabled}
            aria-label={label}
            placeholder="Enter your initial input here..."
            onChange={(event) => onDraftChange({ ...draft, text: event.target.value })}
            className={`h-28 ${fieldClass}`}
          />
          <AttachDocument
            value={draft.text}
            disabled={disabled}
            onChange={(text) => onDraftChange({ ...draft, text })}
            onReading={(name) => onReading?.('', name)}
          />
        </div>
      )}
      {/* There even when empty, so screen readers follow it once it speaks. */}
      <p role="status" className="-mt-1 mb-4 text-sm text-amber-300 empty:m-0">
        {tooLong ?? ''}
      </p>
    </>
  );
}

/** One labelled field per declared input; every one must be filled to run. */
function NamedInputFields(props: NamedInputFieldsProps) {
  const { inputs, draft, disabled, onDraftChange, onReading } = props;
  const size = runInputSize(inputs, draft);
  return (
    <div className="mb-4 grid gap-4 md:grid-cols-2">
      {inputs.map((field) => (
        <NamedInputField
          key={field.name}
          field={field}
          draft={draft}
          others={size - (draft.values[field.name] ?? '').length}
          disabled={disabled}
          onDraftChange={onDraftChange}
          onReading={onReading}
        />
      ))}
    </div>
  );
}

interface NamedInputFieldProps extends Omit<NamedInputFieldsProps, 'inputs'> {
  field: PipelineInput;
  /** Characters the run's other inputs take. */
  others: number;
}

/**
 * The documents input's description says their text is put there, which is only true while
 * the mission's message box holds them; the field itself says how to fill it.
 */
const DOCUMENTS_PLACEHOLDER = 'Attach your documents or web pages below, or paste their text.';

function placeholderOf(field: PipelineInput): string {
  if (field.name === DOCUMENTS_INPUT_NAME) return DOCUMENTS_PLACEHOLDER;
  return field.description || 'Value for this input';
}

/** One input: its label, a text area, and ways to fill it from a document or a web page. */
function NamedInputField(props: NamedInputFieldProps) {
  const { field, draft, others, disabled, onDraftChange, onReading } = props;
  const id = useId();
  const value = draft.values[field.name] ?? '';
  const setValue = (next: string) =>
    onDraftChange({ ...draft, values: { ...draft.values, [field.name]: next } });

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-1.5 flex items-baseline gap-2 text-sm font-medium text-slate-200"
      >
        {inputLabel(field)}
        <code className="text-xs font-normal text-sky-300/80">{`{${field.name}}`}</code>
      </label>
      <textarea
        id={id}
        value={value}
        disabled={disabled}
        placeholder={placeholderOf(field)}
        onChange={(event) => setValue(event.target.value)}
        className={`h-20 ${fieldClass}`}
      />
      <AttachDocument
        value={value}
        others={others}
        disabled={disabled}
        onChange={setValue}
        onReading={(name) => onReading?.(field.name, name)}
      />
    </div>
  );
}
