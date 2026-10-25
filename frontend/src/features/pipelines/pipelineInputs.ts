import type { ExtractedDocument, PipelineInput, PipelineRunRequest } from '../../core/api/types';
import { parseCost } from '../../core/usageFormat';

/**
 * Named run inputs. The naming rule mirrors `input_name_error` in
 * backend/api/services/pipeline_inputs.py, which decides for real; checking it
 * here only shows problems before a save.
 */
const NAME_PATTERN = /^[a-z][a-z0-9_]*$/;
const NAME_MAX_LENGTH = 40;
/** `{input}` is each stage's input, so no named input may take that name. */
export const STAGE_INPUT = 'input';
const PLACEHOLDER = /\{([a-z][a-z0-9_]*)\}/g;

/** What the run form holds: free text, or a value per named input, and an optional cost limit. */
export interface RunDraft {
  text: string;
  values: Record<string, string>;
  /** "Stop if it costs more than $…" as typed; empty or missing means no limit of its own. */
  maxCost?: string;
}

export const EMPTY_RUN_DRAFT: RunDraft = { text: '', values: {} };

/** Lowercase snake_case as the user types, so the name works as `{name}`. */
export function toInputName(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/[^a-z0-9_]/g, '')
    .slice(0, NAME_MAX_LENGTH);
}

/** Why an input's name cannot be saved, or null when it can. */
export function inputNameProblem(name: string, inputs: PipelineInput[]): string | null {
  if (!NAME_PATTERN.test(name)) return 'Start with a letter; use only a–z, 0–9 and _.';
  if (name === STAGE_INPUT) return '"input" is reserved for the stage input.';
  const uses = inputs.filter((field) => field.name === name).length;
  if (uses > 1) return 'Another input has this name.';
  return null;
}

/** Append an input with the first free `field_N` name. */
export function addInput(inputs: PipelineInput[]): PipelineInput[] {
  const taken = new Set(inputs.map((field) => field.name));
  let index = inputs.length + 1;
  while (taken.has(`field_${index}`)) index += 1;
  return [...inputs, { name: `field_${index}`, label: '', description: '' }];
}

export function inputLabel(field: PipelineInput): string {
  return field.label.trim() || field.name;
}

/** The diagram's Input terminal: the declared inputs, else the typed text. */
export function inputsSummary(inputs: PipelineInput[], text: string): string {
  return inputs.length > 0 ? inputs.map(inputLabel).join(' · ') : text || 'Your text';
}

/** Placeholders in a prompt that neither `{input}` nor a declared input fills. */
export function unknownPlaceholders(prompt: string, inputs: PipelineInput[]): string[] {
  const known = new Set([STAGE_INPUT, ...inputs.map((field) => field.name)]);
  const used = [...prompt.matchAll(PLACEHOLDER)].map((match) => match[1]);
  return [...new Set(used)].filter((name) => !known.has(name));
}

/**
 * Why the typed cost limit cannot be used, or null when it is empty (no limit) or fine.
 * A limit that is typed but unusable must stop the run from starting: running
 * without the cap the person asked for would be worse than not running.
 */
export function costLimitProblem(draft: RunDraft): string | null {
  const typed = draft.maxCost ?? '';
  if (typed.trim() === '' || parseCost(typed) !== null) return null;
  return 'Enter an amount above zero, like 0.50, or leave it empty.';
}

export function isRunReady(inputs: PipelineInput[], draft: RunDraft): boolean {
  if (costLimitProblem(draft) !== null) return false;
  if (inputs.length === 0) return draft.text.trim() !== '';
  return inputs.every((field) => (draft.values[field.name] ?? '').trim() !== '');
}

/** The run body: the text, or a value for each declared input, and the cost limit if one is set. */
export function runRequest(inputs: PipelineInput[], draft: RunDraft): PipelineRunRequest {
  const limit = parseCost(draft.maxCost ?? '');
  const budget = limit === null ? {} : { max_cost_usd: limit };
  if (inputs.length === 0) return { input: draft.text, ...budget };
  return {
    inputs: Object.fromEntries(inputs.map((field) => [field.name, draft.values[field.name] ?? ''])),
    ...budget,
  };
}

/**
 * `current` with a document's text added under a line naming its source, so the model
 * knows where it came from. Anything already typed is kept, with a blank line between.
 */
export function appendDocument(current: string, document: ExtractedDocument): string {
  const block = `[Document: ${document.filename}]\n${document.text}`;
  return current.trim() ? `${current.trimEnd()}\n\n${block}` : block;
}

/**
 * One line telling the person what was added, and warning when part was left out: cut
 * at a limit, or pages text recognition skipped (the text itself says which).
 */
export function documentSummary(document: ExtractedDocument): string {
  const pages =
    document.pages === null ? '' : ` · ${document.pages} page${document.pages === 1 ? '' : 's'}`;
  const added = `${document.filename} added${pages} · ${document.characters.toLocaleString('en-US')} characters`;
  return document.truncated ? `${added} · part of it was left out` : added;
}
