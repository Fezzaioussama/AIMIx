import type { ExtractedDocument, PipelineInput, PipelineRunRequest } from '../../core/api/types';
import { formatCount, parseCost } from '../../core/usageFormat';
import { bareLink, sameAddress, sourceLabel } from './webLinks';

/**
 * Named run inputs. The naming rule mirrors `input_name_error` in
 * backend/api/services/pipeline_inputs.py, which decides for real; checking it
 * here only shows problems before a save.
 */
const NAME_PATTERN = /^[a-z][a-z0-9_]*$/;
const NAME_MAX_LENGTH = 40;
/** `{input}` is each stage's input, and `{feedback}` a reviewer's feedback (see below). */
export const STAGE_INPUT = 'input';
export const REVIEW_FEEDBACK = 'feedback';
/** The names the engine fills itself, so no named input may take them, with why. */
const RESERVED_NAMES: Record<string, string> = {
  [STAGE_INPUT]: '"input" is reserved for the stage input.',
  [REVIEW_FEEDBACK]: '"feedback" is reserved for a reviewer’s feedback.',
};
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
  if (Object.hasOwn(RESERVED_NAMES, name)) return RESERVED_NAMES[name];
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

/** Placeholders in a prompt that neither `{input}`, `{feedback}` nor a declared input fills. */
export function unknownPlaceholders(prompt: string, inputs: PipelineInput[]): string[] {
  const known = new Set([...Object.keys(RESERVED_NAMES), ...inputs.map((field) => field.name)]);
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

/**
 * Characters one run may be given in all: its text, or its named inputs together. Mirrors
 * RUN_INPUT_MAX_LENGTH in backend/api/schemas/common.py, which decides.
 */
export const RUN_INPUT_MAX_LENGTH = 500_000;

/** The characters a run would be given (what `runRequest` sends). */
export function runInputSize(inputs: PipelineInput[], draft: RunDraft): number {
  if (inputs.length === 0) return draft.text.length;
  return inputs.reduce((size, field) => size + (draft.values[field.name] ?? '').length, 0);
}

/** Why the inputs are too long for one run, or null when they fit. */
export function runInputLimitProblem(inputs: PipelineInput[], draft: RunDraft): string | null {
  const size = runInputSize(inputs, draft);
  if (size <= RUN_INPUT_MAX_LENGTH) return null;
  return (
    `Your inputs are ${formatCount(size)} characters; a run takes at most ` +
    `${formatCount(RUN_INPUT_MAX_LENGTH)}. Shorten the text, or delete a document from it ` +
    '(each starts with “[Document: …]”).'
  );
}

/**
 * Why `document` should not be added without asking: with it, the run's inputs would be
 * `size` characters, past the limit. Null when it fits.
 */
export function documentLimitWarning(document: ExtractedDocument, size: number): string | null {
  if (size <= RUN_INPUT_MAX_LENGTH) return null;
  return (
    `Adding ${sourceLabel(document.filename)} would make your inputs ${formatCount(size)} ` +
    `characters; a run takes at most ${formatCount(RUN_INPUT_MAX_LENGTH)}.`
  );
}

export function isRunReady(inputs: PipelineInput[], draft: RunDraft): boolean {
  if (costLimitProblem(draft) !== null || runInputLimitProblem(inputs, draft) !== null) {
    return false;
  }
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
  const block = documentBlock(document);
  return current.trim() ? `${current.trimEnd()}\n\n${block}` : block;
}

function documentBlock(document: ExtractedDocument): string {
  return `${documentHeader(document.filename)}\n${document.text}`;
}

/** The line a document's text starts with in an input, naming where it came from. */
function documentHeader(filename: string): string {
  return `[Document: ${filename}]`;
}

/** Whether `current` still holds the document added from `filename` (its header line). */
export function holdsDocument(current: string, filename: string): boolean {
  return current.includes(documentHeader(filename));
}

/**
 * `current` with a document in it, added after what is there (`appendDocument`). A page
 * read from `link`, the link the input holds alone, takes that link's place instead.
 */
export function placeDocument(
  current: string,
  document: ExtractedDocument,
  link: string | null,
): string {
  const held = bareLink(current);
  if (link !== null && held !== null && sameAddress(held, link)) return documentBlock(document);
  return appendDocument(current, document);
}

/** "2 pages · 24,310 characters" (no pages for unpaged formats), from a document's size. */
export function documentSize({
  pages,
  characters,
}: Pick<ExtractedDocument, 'pages' | 'characters'>): string {
  const size = `${formatCount(characters)} characters`;
  return pages === null ? size : `${pages} page${pages === 1 ? '' : 's'} · ${size}`;
}

/**
 * A document's size, warning when part was left out: cut at a limit, or pages text
 * recognition skipped (the text itself says which).
 */
export function documentDetails(document: ExtractedDocument): string {
  const size = documentSize(document);
  return document.truncated ? `${size} · part of it was left out` : size;
}

/** Why something waits (a run, a plan): `name`, a document or page, is still being read. */
export function waitingForDocument(name: string): string {
  return `Waiting for ${name} to be read…`;
}

/** One line telling the person what was added: the file's name, or the page's link. */
export function documentSummary(document: ExtractedDocument): string {
  return `${sourceLabel(document.filename)} added · ${documentDetails(document)}`;
}
