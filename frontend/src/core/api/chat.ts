import { ApiError, streamText } from './client';
import type { ChatEvent } from './chatTypes';
import { API } from './endpoints';

/** Decodes one NDJSON line; anything else means the server broke its contract. */
function parseEvent(line: string): ChatEvent {
  try {
    return JSON.parse(line) as ChatEvent;
  } catch {
    throw new ApiError('The chat reply could not be read.', 0, 'invalid_response');
  }
}

/** What goes with a message: the chat it belongs to (the server reads what was said there), and where the person is. */
export interface ChatContext {
  chatId: number;
  /** The browser's IANA time zone, so "every Monday at 9" means 9 where the person is. */
  timezone: string;
}

/**
 * Streams a chat reply's events as they arrive. The endpoint answers one JSON
 * object per line (NDJSON), so a line that spans chunks is buffered until its
 * newline.
 */
export async function* streamChatReply(
  prompt: string,
  context: ChatContext,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  let buffer = '';
  const body = { prompt, chat_id: context.chatId, timezone: context.timezone };
  for await (const chunk of streamText(API.chat, body, signal, 'application/x-ndjson')) {
    buffer += chunk;
    let newline = buffer.indexOf('\n');
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) yield parseEvent(line);
      newline = buffer.indexOf('\n');
    }
  }
  const rest = buffer.trim();
  if (rest) yield parseEvent(rest);
}
