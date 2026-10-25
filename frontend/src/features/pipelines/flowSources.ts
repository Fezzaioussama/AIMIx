/**
 * What a condition can look at, as the `source` text a step stores. Mirrors
 * `CONDITION_SOURCES` in backend/api/services/multiagent/conditions.py, which decides for
 * real; this leaf module imports nothing, so every other flow module can use it.
 */

/** What the previous stage handed on: the step's `{input}` (in the first stage, the run's text). */
export const PREVIOUS_OUTPUT = 'previous_output';

/** A condition that looks at a step that was removed: no step has the number 0. */
export const REMOVED_STEP_SOURCE = 'step:0';

export function inputSource(name: string): string {
  return `input:${name}`;
}

export function stepSource(order: number): string {
  return `step:${order}`;
}

/** `input:topic` as `{ kind: 'input', key: 'topic' }`; a source without a key has `key: ''`. */
export function parseSource(source: string): { kind: string; key: string } {
  const [kind, ...rest] = source.trim().split(':');
  return { kind: kind.trim(), key: rest.join(':').trim() };
}

/** The number of the step a `step:` source names; null for any other source. */
export function stepOrderOf(source: string): number | null {
  const { kind, key } = parseSource(source);
  return kind === 'step' && /^[0-9]+$/.test(key) ? Number(key) : null;
}

/** The name of the input an `input:` source names; null for any other source. */
export function inputNameOf(source: string): string | null {
  const { kind, key } = parseSource(source);
  return kind === 'input' ? key : null;
}
