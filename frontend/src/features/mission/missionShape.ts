import type { Pipeline } from '../../core/api/types';
import {
  INPUTS_STATES,
  NOTE_TONES,
  PROPOSAL_STATES,
  QUESTIONS_STATES,
  TEAM_ORIGINS,
  type AimixMessage,
  type MissionMessage,
} from './missionMessages';

/**
 * What a conversation read back from the tab's storage must look like to be drawn. It was
 * written by this app, but possibly by an older version: anything that does not fit is
 * left out rather than allowed to break the screen (storage is untrusted input).
 */

type Fields = Record<string, unknown>;

export function isRecord(value: unknown): value is Fields {
  return typeof value === 'object' && value !== null;
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number';
}

function oneOf(values: readonly string[], value: unknown): boolean {
  return isString(value) && values.includes(value);
}

function listOf(guard: (item: unknown) => boolean, value: unknown): boolean {
  return Array.isArray(value) && value.every(guard);
}

const TOOL_KINDS = ['all', 'none', 'some'];

function isAgent(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.order) &&
    isString(value.name) &&
    isString(value.task) &&
    typeof value.deliverable === 'boolean' &&
    isRecord(value.tools) &&
    oneOf(TOOL_KINDS, value.tools.kind) &&
    listOf(isString, value.tools.names)
  );
}

function isBrief(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.name) &&
    isNumber(value.stages) &&
    listOf(isAgent, value.agents) &&
    listOf(isString, value.provides)
  );
}

function isQuestion(value: unknown): boolean {
  return isRecord(value) && isString(value.question) && listOf(isString, value.options);
}

function isChange(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.target) &&
    isString(value.kind) &&
    isString(value.label) &&
    listOf(isString, value.fields)
  );
}

/** The fields each kind of answer needs to be drawn (a registry: a new kind adds an entry). */
const AIMIX_FIELDS: Record<AimixMessage['kind'], (message: Fields) => boolean> = {
  note: (message) => isString(message.text) && oneOf(NOTE_TONES, message.tone),
  team: (message) => oneOf(TEAM_ORIGINS, message.origin) && isBrief(message.brief),
  questions: (message) =>
    oneOf(QUESTIONS_STATES, message.state) &&
    isString(message.description) &&
    listOf(isQuestion, message.questions),
  proposal: (message) =>
    oneOf(PROPOSAL_STATES, message.state) &&
    listOf(isChange, message.changes) &&
    isString(message.error),
  inputs: (message) => oneOf(INPUTS_STATES, message.state),
  run: (message) => isNumber(message.runId),
};

export function isMessage(value: unknown): value is MissionMessage {
  if (!isRecord(value) || !isString(value.id)) return false;
  if (value.from === 'you') return isString(value.text);
  if (value.from !== 'aimix' || !isString(value.kind)) return false;
  if (!Object.hasOwn(AIMIX_FIELDS, value.kind)) return false;
  return AIMIX_FIELDS[value.kind as AimixMessage['kind']](value);
}

function isInput(value: unknown): boolean {
  return (
    isRecord(value) && isString(value.name) && isString(value.label) && isString(value.description)
  );
}

/** A step's condition, when it has one: drafts kept before conditions existed have none. */
function isCondition(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    (isRecord(value) && isString(value.source) && isString(value.operator) && isString(value.value))
  );
}

/** A step's review, when it has one: drafts kept before review loops existed have none. */
function isReview(value: unknown): boolean {
  return (
    value === undefined ||
    value === null ||
    (isRecord(value) && isNumber(value.send_back_to_stage) && isNumber(value.max_rounds))
  );
}

function isStep(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNumber(value.order) &&
    isNumber(value.stage) &&
    typeof value.is_output === 'boolean' &&
    [value.title, value.expected_output, value.prompt, value.model, value.role].every(isString) &&
    (value.allowed_tools === null || listOf(isString, value.allowed_tools)) &&
    isCondition(value.condition) &&
    isReview(value.review)
  );
}

/** A draft team as the page needs it: named, with well-formed inputs and steps. */
export function isPipeline(value: unknown): value is Pipeline {
  return (
    isRecord(value) &&
    isString(value.name) &&
    listOf(isInput, value.inputs) &&
    listOf(isStep, value.steps)
  );
}
