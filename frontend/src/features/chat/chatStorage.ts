import { CHAT_ACTION_KINDS, type ChatAction } from '../../core/api/chatTypes';
import { isRecord } from '../mission/missionShape';
import type { ChatMessage, ChatToolRun } from './useChatStream';

/**
 * The chat's conversation for this browser tab (sessionStorage), so opening what the
 * assistant built and coming back continues it. Every access is wrapped: blocked or full
 * storage only means nothing is kept.
 */

/** Versioned, so a later change of the message shape starts from a clean slate. */
const KEY = 'aimix.chat.v1';
/** Older messages are dropped past this, so one long conversation never fills the storage. */
export const MAX_STORED_MESSAGES = 200;

export function readChat(): ChatMessage[] {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? value.flatMap(restoredMessage) : [];
  } catch {
    return [];
  }
}

export function writeChat(messages: ChatMessage[]): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(messages.slice(-MAX_STORED_MESSAGES)));
  } catch {
    // Full or blocked storage: the conversation still works for this visit.
  }
}

/**
 * Forgets the conversation: a new chat, or the session ending. The key names no
 * account, so it goes with the session (main.tsx), like the missions kept in the tab.
 */
export function forgetChat(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing could be kept, so there is nothing to forget.
  }
}

function restoredMessage(value: unknown): ChatMessage[] {
  if (!isRecord(value)) return [];
  const { id, text, sender, timestamp, tools, failed } = value;
  if (typeof id !== 'number' || typeof text !== 'string' || typeof timestamp !== 'string')
    return [];
  if (sender !== 'user' && sender !== 'ai') return [];
  const time = new Date(timestamp);
  if (Number.isNaN(time.getTime())) return [];
  return [
    {
      id,
      text,
      sender,
      timestamp: time,
      tools: Array.isArray(tools) ? tools.flatMap(restoredTool) : [],
      ...(failed === true && { failed: true }),
    },
  ];
}

/** A tool still running when the chat was left shows as stopped: its reply never came. */
function restoredTool(value: unknown): ChatToolRun[] {
  if (!isRecord(value)) return [];
  const { id, tool, label, status, detail, action } = value;
  if (typeof id !== 'string' || typeof tool !== 'string' || typeof label !== 'string') return [];
  const ended = status === 'finished' || status === 'failed';
  return [
    {
      id,
      tool,
      label,
      status: ended ? status : 'failed',
      detail: ended ? (typeof detail === 'string' ? detail : undefined) : 'Stopped',
      action: isAction(action) ? action : undefined,
    },
  ];
}

function isAction(value: unknown): value is ChatAction {
  return (
    isRecord(value) &&
    CHAT_ACTION_KINDS.some((kind) => kind === value.kind) &&
    typeof value.id === 'number' &&
    typeof value.title === 'string' &&
    typeof value.subtitle === 'string'
  );
}
