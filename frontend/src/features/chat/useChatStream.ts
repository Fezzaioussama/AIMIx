import { useCallback, useEffect, useRef, useState } from 'react';

import { streamChatReply } from '../../core/api/chat';
import type { ChatAction, ChatToolEvent, ChatToolStatus } from '../../core/api/chatTypes';

/** One tool the assistant used, and what it produced. */
export interface ChatToolRun {
  id: string;
  tool: string;
  label: string;
  status: ChatToolStatus;
  detail?: string;
  action?: ChatAction;
}

export interface ChatMessage {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  timestamp: Date;
  tools: ChatToolRun[];
}

const GREETING = 'Hello! I am your AI assistant. How can I help you today?';

function greeting(): ChatMessage {
  return { id: 0, text: GREETING, sender: 'ai', timestamp: new Date(), tools: [] };
}

/**
 * Owns the chat transcript, the tools each reply used, and the streaming read
 * loop, keeping transport out of the component (AGENTS.md §2).
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

  const applyTool = useCallback((id: number, event: ChatToolEvent) => {
    setMessages((current) =>
      current.map((message) => {
        if (message.id !== id) return message;
        if (event.status === 'started') {
          return {
            ...message,
            tools: [
              ...message.tools,
              {
                id: `${id}-${message.tools.length}`,
                tool: event.tool,
                label: event.label,
                status: event.status,
              },
            ],
          };
        }
        // The event closes the newest run of that tool still waiting for its result.
        let running = -1;
        for (let index = message.tools.length - 1; index >= 0; index -= 1) {
          const tool = message.tools[index];
          if (tool?.tool === event.tool && tool.status === 'started') {
            running = index;
            break;
          }
        }
        const updated = {
          status: event.status,
          detail: event.detail,
          action: event.action,
        };
        return {
          ...message,
          tools:
            running === -1
              ? [
                  ...message.tools,
                  {
                    id: `${id}-${message.tools.length}`,
                    tool: event.tool,
                    label: event.label,
                    ...updated,
                  },
                ]
              : message.tools.map((tool, index) =>
                  index === running ? { ...tool, ...updated } : tool,
                ),
        };
      }),
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
        { id: replyId - 1, text: trimmed, sender: 'user', timestamp: new Date(), tools: [] },
        { id: replyId, text: '', sender: 'ai', timestamp: new Date(), tools: [] },
      ]);
      setIsLoading(true);

      try {
        for await (const event of streamChatReply(trimmed, controller.signal)) {
          if (event.type === 'text') {
            setIsLoading(false);
            appendChunk(replyId, event.text);
          } else {
            applyTool(replyId, event);
          }
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
    [appendChunk, applyTool],
  );

  return { messages, isLoading, send };
}
