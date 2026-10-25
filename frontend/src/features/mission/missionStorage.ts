import type { Pipeline } from '../../core/api/types';
import {
  INPUTS_STATES,
  NOTE_TONES,
  PROPOSAL_STATES,
  TEAM_ORIGINS,
  type AimixMessage,
  type MissionMessage,
} from './missionMessages';

/**
 * What a mission keeps for this browser tab (sessionStorage): its conversation and,
 * until its first save, its team. Saved missions load their team from the server.
 * Every access is wrapped: blocked or full storage only means nothing is kept.
 */
export interface StoredMission {
  messages: MissionMessage[];
  /** The team of a mission that was never saved; null once the server has it. */
  draft: Pipeline | null;
}

/** Versioned, so a later change of the message shape starts from a clean slate. */
const PREFIX = 'aimix.mission.v1.';
/** Older messages are dropped past this, so one long conversation never fills the storage. */
export const MAX_STORED_MESSAGES = 200;
const EMPTY: StoredMission = { messages: [], draft: null };

/** Where a mission is kept: by its pipeline id, or `new` until its first save. */
export function missionKey(pipelineId?: number): string {
  return `${PREFIX}${pipelineId ?? 'new'}`;
}

export function readMission(key: string): StoredMission {
  try {
    const raw = window.sessionStorage.getItem(key);
    return raw ? parseMission(JSON.parse(raw)) : EMPTY;
  } catch {
    return EMPTY;
  }
}

export function writeMission(key: string, mission: StoredMission): void {
  const kept = { ...mission, messages: mission.messages.slice(-MAX_STORED_MESSAGES) };
  try {
    window.sessionStorage.setItem(key, JSON.stringify(kept));
  } catch {
    // Full or blocked storage: the conversation still works for this visit.
  }
}

export function forgetMission(key: string): void {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    // Nothing could be kept, so there is nothing to forget.
  }
}

type Fields = Record<string, unknown>;

function isRecord(value: unknown): value is Fields {
  return typeof value === 'object' && value !== null;
}

function oneOf(values: readonly string[], value: unknown): boolean {
  return typeof value === 'string' && values.includes(value);
}

/** The fields each kind of answer needs to be drawn; anything else is left out. */
const AIMIX_FIELDS: Record<AimixMessage['kind'], (message: Fields) => boolean> = {
  note: (message) => typeof message.text === 'string' && oneOf(NOTE_TONES, message.tone),
  team: (message) =>
    oneOf(TEAM_ORIGINS, message.origin) &&
    isRecord(message.brief) &&
    Array.isArray(message.brief.agents) &&
    Array.isArray(message.brief.provides),
  proposal: (message) =>
    oneOf(PROPOSAL_STATES, message.state) &&
    Array.isArray(message.changes) &&
    typeof message.error === 'string',
  inputs: (message) => oneOf(INPUTS_STATES, message.state),
  run: (message) => typeof message.runId === 'number',
};

function isMessage(value: unknown): value is MissionMessage {
  if (!isRecord(value) || typeof value.id !== 'string') return false;
  if (value.from === 'you') return typeof value.text === 'string';
  if (value.from !== 'aimix' || typeof value.kind !== 'string') return false;
  if (!Object.hasOwn(AIMIX_FIELDS, value.kind)) return false;
  return AIMIX_FIELDS[value.kind as AimixMessage['kind']](value);
}

function isPipeline(value: unknown): value is Pipeline {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    Array.isArray(value.inputs) &&
    Array.isArray(value.steps)
  );
}

function parseMission(value: unknown): StoredMission {
  if (!isRecord(value)) return EMPTY;
  return {
    messages: Array.isArray(value.messages) ? value.messages.filter(isMessage) : [],
    draft: isPipeline(value.draft) ? value.draft : null,
  };
}
