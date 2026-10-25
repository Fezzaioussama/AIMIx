import type { Pipeline, PipelineChange } from '../../core/api/types';

/**
 * Longest change request the backend accepts. Mirrors REVISION_INSTRUCTION_MAX_LENGTH in
 * backend/api/schemas/pipelines.py, which decides; here it only caps the text box.
 */
export const REVISION_INSTRUCTION_MAX_LENGTH = 2000;

/** Starting points offered under the change box; picking one fills it in. */
export const REVISION_EXAMPLES = [
  'Add an agent that checks the facts before the final answer',
  'Make the research steps run in parallel and let them search the web',
  'Make every output shorter and friendlier',
] as const;

const VERBS: Record<PipelineChange['kind'], string> = {
  added: 'Adds',
  removed: 'Removes',
  changed: 'Changes',
};

/** API field names in plain words, for the change list. */
const FIELD_WORDS: Record<string, string> = {
  prompt: 'instructions',
  expected_output: 'expected result',
  allowed_tools: 'tools',
  stage: 'when it runs',
  is_output: 'whether it is an output',
};

/** "a", "a and b", "a, b and c". */
export function joinWords(words: string[]): string {
  if (words.length < 2) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

/** One change as a short sentence, e.g. `Changes the step “Research”: instructions and tools`. */
export function describeChange(change: PipelineChange): string {
  const name = `“${change.label}”`;
  if (change.target === 'pipeline') return `Renames the pipeline to ${name}`;
  const sentence = `${VERBS[change.kind]} the ${change.target} ${name}`;
  const fields = change.fields.map((field) => FIELD_WORDS[field] ?? field.replace(/_/g, ' '));
  return fields.length > 0 ? `${sentence}: ${joinWords(fields)}` : sentence;
}

/**
 * The revision as the new draft: it keeps the draft's identity, so saving it updates the
 * pipeline it came from rather than creating another one.
 */
export function adoptRevision(draft: Pipeline, revised: Pipeline): Pipeline {
  return { ...revised, id: draft.id };
}
