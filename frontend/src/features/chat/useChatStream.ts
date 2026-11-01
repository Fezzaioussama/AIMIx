import { useCallback, useEffect, useRef, useState } from 'react';

import { streamChatReply } from '../../core/api/chat';
import type { ChatAction, ChatToolEvent, ChatToolStatus, ChatTurn } from '../../core/api/chatTypes';
import { browserTimeZone } from '../schedules/scheduleDraft';
import { forgetChat, readChat, writeChat } from './chatStorage';

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
  /** The reply could not be had; it is shown, but the assistant is not told it said so. */
  failed?: boolean;
}

const GREETING_ID = 0;
const GREETING =
  "Hi! Tell me in your own words what you want done, and I'll build the workflow for you: its agents, their tools and when it runs.";

function greeting(): ChatMessage {
  return { id: GREETING_ID, text: GREETING, sender: 'ai', timestamp: new Date(), tools: [] };
}

function restoredOrGreeting(): ChatMessage[] {
  const stored = readChat();
  return stored.length > 0 ? stored : [greeting()];
}

/** The conversation as the assistant reads it: every exchange but the greeting and failed replies. */
export function historyOf(messages: ChatMessage[]): ChatTurn[] {
  return messages
    .filter((message) => message.id !== GREETING_ID && !message.failed && message.text.trim())
    .map((message) => ({
      role: message.sender === 'user' ? 'user' : 'assistant',
      content: message.text,
    }));
}

/**
 * Owns the chat transcript, the tools each reply used, and the streaming read
 * loop, keeping transport out of the component (AGENTS.md §2). The transcript is
 * kept for this tab, and each message carries the conversation before it.
 */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>(restoredOrGreeting);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const latest = useRef(messages);

  // Keep the conversation once each reply is complete, not on every streamed word.
  useEffect(() => {
    latest.current = messages;
    if (!isStreaming) writeChat(messages);
  }, [messages, isStreaming]);

  // Leaving mid-reply (to open what the assistant built) stops it and keeps what came.
  useEffect(
    () => () => {
      abortRef.current?.abort();
      writeChat(latest.current);
    },
    [],
  );

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

  const fail = useCallback((id: number, text: string) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id ? { ...message, text: message.text + text, failed: true } : message,
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
      const context = { history: historyOf(messages), timezone: browserTimeZone() };

      setMessages((current) => [
        ...current,
        { id: replyId - 1, text: trimmed, sender: 'user', timestamp: new Date(), tools: [] },
        { id: replyId, text: '', sender: 'ai', timestamp: new Date(), tools: [] },
      ]);
      setIsLoading(true);
      setIsStreaming(true);

      try {
        for await (const event of streamChatReply(trimmed, context, controller.signal)) {
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
        fail(replyId, message);
      } finally {
        setIsLoading(false);
        setIsStreaming(false);
      }
    },
    [appendChunk, applyTool, fail, messages],
  );

  /** Starts over: stops a reply in progress and forgets the conversation. */
  const reset = useCallback(() => {
    abortRef.current?.abort();
    forgetChat();
    setMessages([greeting()]);
  }, []);

  return { messages, isLoading, send, reset };
}
