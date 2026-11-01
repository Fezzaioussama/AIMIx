/**
 * The events a chat reply streams (POST /api/chat, NDJSON): its text, and the
 * tools it used, so the chat can show what the agent is doing and link to what
 * it created.
 */

export type ChatToolStatus = 'started' | 'finished' | 'failed';

/** One earlier message, sent with the next one so the assistant remembers the conversation. */
export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

/** What a finished tool can link to. */
export const CHAT_ACTION_KINDS = ['pipeline', 'schedule', 'run', 'webhook', 'delivery'] as const;
export type ChatActionKind = (typeof CHAT_ACTION_KINDS)[number];

/** A thing a finished tool created, which the chat offers as a link. */
export interface ChatAction {
  kind: ChatActionKind;
  id: number;
  title: string;
  subtitle: string;
}

export interface ChatTextEvent {
  type: 'text';
  text: string;
}

export interface ChatToolEvent {
  type: 'tool';
  tool: string;
  /** The phrase the chat shows while the tool runs, e.g. "Creating a schedule". */
  label: string;
  status: ChatToolStatus;
  detail?: string;
  action?: ChatAction;
}

export type ChatEvent = ChatTextEvent | ChatToolEvent;
