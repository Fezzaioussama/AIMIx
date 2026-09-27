import { API } from './endpoints';
import { streamText } from './client';

export function streamChatReply(prompt: string, signal?: AbortSignal): AsyncGenerator<string> {
  return streamText(API.chat, { prompt }, signal);
}
