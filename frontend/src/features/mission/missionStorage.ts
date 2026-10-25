import type { Pipeline } from '../../core/api/types';
import { restoredMessages, type MissionMessage } from './missionMessages';
import { isMessage, isPipeline, isRecord } from './missionShape';

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

/** A mission as it was left in this tab, ready to continue (see `restoredMessages`). */
export function restoreMission(pipelineId?: number): StoredMission {
  const stored = readMission(missionKey(pipelineId));
  return { ...stored, messages: restoredMessages(stored.messages) };
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

function parseMission(value: unknown): StoredMission {
  if (!isRecord(value)) return EMPTY;
  return {
    messages: Array.isArray(value.messages) ? value.messages.filter(isMessage) : [],
    draft: isPipeline(value.draft) ? value.draft : null,
  };
}
