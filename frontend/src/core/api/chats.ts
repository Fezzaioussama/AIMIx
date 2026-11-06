import { request } from './client';
import type { ChatDetail, ChatSummary } from './chatTypes';
import { API } from './endpoints';

/** The chats the server keeps for the signed-in person, the one last written to first. */
export function listChats(signal?: AbortSignal): Promise<ChatSummary[]> {
  return request<ChatSummary[]>(API.chats, { signal });
}

/** A new, empty chat; left untitled, it takes its first message's first line as its title. */
export function createChat(title = ''): Promise<ChatSummary> {
  return request<ChatSummary>(API.chats, { method: 'POST', body: { title } });
}

export function getChat(chatId: number, signal?: AbortSignal): Promise<ChatDetail> {
  return request<ChatDetail>(API.chatById(chatId), { signal });
}

export function renameChat(chatId: number, title: string): Promise<ChatSummary> {
  return request<ChatSummary>(API.chatById(chatId), { method: 'PATCH', body: { title } });
}

/** Delete a chat and everything said in it. */
export function deleteChat(chatId: number): Promise<void> {
  return request<void>(API.chatById(chatId), { method: 'DELETE' });
}
