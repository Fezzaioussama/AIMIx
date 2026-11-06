import { useCallback, useEffect, useRef, useState } from 'react';

import { streamChatReply } from '../../core/api/chat';
import { getChat } from '../../core/api/chats';
import type {
  ChatAction,
  ChatSavedMessage,
  ChatToolEvent,
  ChatToolStatus,
} from '../../core/api/chatTypes';
import { errorMessage } from '../../core/api/errorMessage';
import type { Usage } from '../../core/api/types';
import { browserTimeZone } from '../schedules/scheduleDraft';

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
  /** What the reply's model calls used, once it ended. */
  usage?: Usage;
}

const GREETING_ID = 0;
const GREETING =
  "Hi! Tell me in your own words what you want done, and I'll build the workflow for you: its agents, their tools and when it runs.";

function greeting(): ChatMessage {
  return { id: GREETING_ID, text: GREETING, sender: 'ai', timestamp: new Date(), tools: [] };
}

/** A saved message as the screen shows it; a tool still running when the reply was cut shows as stopped. */
function restored(message: ChatSavedMessage): ChatMessage {
  return {
    id: message.id,
    text: message.text,
    sender: message.role === 'user' ? 'user' : 'ai',
    timestamp: new Date(message.created_at),
    tools: message.tools.map((tool, index) => {
      const ended = tool.status !== 'started';
      return {
        id: `${message.id}-${index}`,
        tool: tool.tool,
        label: tool.label,
        status: ended ? tool.status : 'failed',
        detail: ended ? tool.detail || undefined : 'Stopped',
        action: tool.action ?? undefined,
      };
    }),
    ...(message.role === 'assistant' && { usage: message.usage }),
  };
}

interface ChatStreamOptions {
  /** The open chat, whose messages are shown; null is a fresh chat. */
  chatId: number | null;
  /** The chat to send in: the open one, or a new one made for the first message. */
  ensureChat: () => Promise<number>;
  /** Called once a reply ends, so the list shows the chat's new title and time. */
  onReplyEnd: () => void;
}

/**
 * Owns the transcript of the open chat, the tools each reply used, and the streaming
 * read loop, keeping transport out of the component (AGENTS.md §2). The chat lives on
 * the server: opening one loads its messages, and each message is sent to it.
 */
export function useChatStream({ chatId, ensureChat, onReplyEnd }: ChatStreamOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([greeting()]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadError, setLoadError] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  // The chat whose messages are on screen; a chat made by `send` is not loaded again.
  const shown = useRef<number | null>(null);

  useEffect(() => {
    if (chatId === shown.current) return;
    // A reply in progress belongs to the chat being left.
    abortRef.current?.abort();
    shown.current = chatId;
    setLoadError('');
    if (chatId === null) {
      setMessages([greeting()]);
      return;
    }
    const controller = new AbortController();
    setLoadingChat(true);
    getChat(chatId, controller.signal)
      .then((chat) => setMessages([greeting(), ...chat.messages.map(restored)]))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setLoadError(errorMessage(cause, 'Could not open this chat.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingChat(false);
      });
    return () => controller.abort();
  }, [chatId]);

  // Leaving mid-reply (to open what the assistant built) stops it; the server keeps what came.
  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = useCallback((id: number, change: (message: ChatMessage) => ChatMessage) => {
    setMessages((current) =>
      current.map((message) => (message.id === id ? change(message) : message)),
    );
  }, []);

  const applyTool = useCallback(
    (id: number, event: ChatToolEvent) => {
      patch(id, (message) => {
        if (event.status === 'started') {
          const run = { id: `${id}-${message.tools.length}`, tool: event.tool, label: event.label };
          return { ...message, tools: [...message.tools, { ...run, status: event.status }] };
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
        const updated = { status: event.status, detail: event.detail, action: event.action };
        if (running === -1) {
          const run = { id: `${id}-${message.tools.length}`, tool: event.tool, label: event.label };
          return { ...message, tools: [...message.tools, { ...run, ...updated }] };
        }
        return {
          ...message,
          tools: message.tools.map((tool, index) =>
            index === running ? { ...tool, ...updated } : tool,
          ),
        };
      });
    },
    [patch],
  );

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
        const id = chatId ?? (await ensureChat());
        shown.current = id;
        const context = { chatId: id, timezone: browserTimeZone() };
        for await (const event of streamChatReply(trimmed, context, controller.signal)) {
          if (event.type === 'text') {
            setIsLoading(false);
            patch(replyId, (message) => ({ ...message, text: message.text + event.text }));
          } else if (event.type === 'tool') {
            applyTool(replyId, event);
          } else {
            patch(replyId, (message) => ({ ...message, usage: event.usage }));
          }
        }
        onReplyEnd();
      } catch (cause) {
        if (controller.signal.aborted) return;
        const text =
          cause instanceof Error
            ? cause.message
            : 'Sorry, I encountered an error. Please check your connection or API key.';
        patch(replyId, (message) => ({ ...message, text: message.text + text, failed: true }));
      } finally {
        setIsLoading(false);
      }
    },
    [applyTool, chatId, ensureChat, onReplyEnd, patch],
  );

  return { messages, isLoading, loadingChat, loadError, send };
}
