import { useCallback, useEffect, useRef, useState } from 'react';

import { createChat, deleteChat, listChats, renameChat } from '../../core/api/chats';
import type { ChatSummary } from '../../core/api/chatTypes';
import { errorMessage } from '../../core/api/errorMessage';
import { readOpenChat, writeOpenChat } from './chatStorage';

/**
 * The person's chats on the server, the one last written to first, and which one is
 * open (kept for the tab, so coming back continues it). A chat is made on the server
 * when its first message is sent (`ensure`), not when "New chat" is pressed, so the
 * list never fills with empty chats.
 */
export function useChats() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [openId, setOpenId] = useState<number | null>(readOpenChat);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => writeOpenChat(openId), [openId]);

  /** The list again: on arrival, and once a reply ends (a new title, a newer time). */
  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const listed = await listChats(signal);
      if (!mounted.current) return;
      setChats(listed);
      setError('');
    } catch (cause) {
      if (!signal?.aborted && mounted.current)
        setError(errorMessage(cause, 'Could not load your chats.'));
    } finally {
      if (!signal?.aborted && mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  /** The chat to send a message in: the open one, or a new one made now. */
  const ensure = useCallback(async (): Promise<number> => {
    if (openId !== null) return openId;
    const made = await createChat();
    if (mounted.current) {
      setChats((known) => [made, ...known]);
      setOpenId(made.id);
    }
    return made.id;
  }, [openId]);

  const select = useCallback((chatId: number) => setOpenId(chatId), []);

  /** A fresh chat: nothing is made on the server until something is said. */
  const startNew = useCallback(() => setOpenId(null), []);

  /** Name a chat; true once it is renamed. */
  const rename = useCallback(async (chatId: number, title: string) => {
    try {
      const updated = await renameChat(chatId, title);
      if (mounted.current) {
        setChats((known) => known.map((chat) => (chat.id === chatId ? updated : chat)));
        setError('');
      }
      return true;
    } catch (cause) {
      if (mounted.current) setError(errorMessage(cause, 'Could not rename this chat.'));
      return false;
    }
  }, []);

  /** Delete a chat and everything said in it; true once it is gone. */
  const remove = useCallback(async (chatId: number) => {
    try {
      await deleteChat(chatId);
    } catch (cause) {
      if (mounted.current) setError(errorMessage(cause, 'Could not delete this chat.'));
      return false;
    }
    if (mounted.current) {
      setChats((known) => known.filter((chat) => chat.id !== chatId));
      setOpenId((current) => (current === chatId ? null : current));
      setError('');
    }
    return true;
  }, []);

  return { chats, openId, loading, error, ensure, select, startNew, rename, remove, refresh };
}
