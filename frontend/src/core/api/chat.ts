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

/**
 * Streams a chat reply's events as they arrive. The endpoint answers one JSON
 * object per line (NDJSON), so a line that spans chunks is buffered until its
 * newline.
 */
export async function* streamChatReply(
  prompt: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  let buffer = '';
  for await (const chunk of streamText(API.chat, { prompt }, signal, 'application/x-ndjson')) {
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
