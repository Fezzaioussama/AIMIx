/**
 * The events a chat reply streams (POST /api/chat, NDJSON): its text, the tools it
 * used, so the chat can show what the agent is doing and link to what it created,
 * and last what its model calls used; and the chats the server keeps (/api/chats).
 */

import type { Usage } from './types';

export type ChatToolStatus = 'started' | 'finished' | 'failed';

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

/** The last event of a reply: what its model calls used and cost in all. */
export interface ChatUsageEvent {
  type: 'usage';
  usage: Usage;
}

export type ChatEvent = ChatTextEvent | ChatToolEvent | ChatUsageEvent;

/** A chat kept on the server, as the list shows it: never its messages. */
export interface ChatSummary {
  id: number;
  /** The first line of its first message, or what the person named it; "" until then. */
  title: string;
  created_at: string;
  /** When it was last written to. */
  updated_at: string;
}

/** One tool a saved reply used, as the chat showed it. */
export interface ChatSavedTool {
  tool: string;
  label: string;
  status: ChatToolStatus;
  detail: string;
  action: ChatAction | null;
}

export interface ChatSavedMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  tools: ChatSavedTool[];
  created_at: string;
  usage: Usage;
}

/** A whole chat: its messages, oldest first, and what they used in all. */
export interface ChatDetail extends ChatSummary {
  messages: ChatSavedMessage[];
  usage: Usage;
}
