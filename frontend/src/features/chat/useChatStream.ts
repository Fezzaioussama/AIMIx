import { useCallback, useEffect, useRef, useState } from 'react';

import { streamChatReply } from '../../core/api/chat';

export interface ChatMessage {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  timestamp: Date;
}

const GREETING = 'Hello! I am your AI assistant. How can I help you today?';

function greeting(): ChatMessage {
  return { id: 0, text: GREETING, sender: 'ai', timestamp: new Date() };
}

/**
 * Owns the chat transcript and the streaming read loop, keeping transport out
 * of the component (AGENTS.md §2).
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [greeting()]);
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Abort an in-flight stream if the screen unmounts mid-reply.
  useEffect(() => () => abortRef.current?.abort(), []);

  const appendChunk = useCallback((id: number, chunk: string) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? { ...message, text: message.text + chunk } : message,
      ),
    );
  }, []);

  const send = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;

      const controller = new AbortController();
      abortRef.current = controller;
      const replyId = Date.now();

      setMessages((current) => [
        ...current,
        { id: replyId - 1, text: trimmed, sender: 'user', timestamp: new Date() },
        { id: replyId, text: '', sender: 'ai', timestamp: new Date() },
      ]);
      setIsLoading(true);

      try {
        for await (const chunk of streamChatReply(trimmed, controller.signal)) {
          setIsLoading(false);
          appendChunk(replyId, chunk);
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        const message =
          cause instanceof Error
            ? cause.message
            : 'Sorry, I encountered an error. Please check your connection or API key.';
        appendChunk(replyId, message);
      } finally {
        setIsLoading(false);
      }
    },
    [appendChunk],
  );

  return { messages, isLoading, send };
}
