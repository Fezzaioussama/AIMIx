import { PanelLeft, SquarePen, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { CostText } from '../../core/ui/CostText';
import { FOCUS_RING } from '../../core/ui/focus';
import { Aurora } from '../../core/ui/reactbits/Aurora';
import { FULL_SCREEN_HEIGHT } from '../../core/ui/screen';
import { describeCost } from '../../core/usageFormat';
import { ChatComposer } from './ChatComposer';
import { ChatList, UNTITLED_CHAT } from './ChatList';
import { ChatSuggestions, MessageBubble, TypingIndicator } from './ChatMessages';
import { totalUsage } from './chatUsage';
import { useChats } from './useChats';
import { useChatStream } from './useChatStream';

const HEADER_BUTTON = `inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-sm text-slate-300 transition hover:border-white/20 hover:text-white ${FOCUS_RING}`;

interface ChatHeaderProps {
  /** The open chat's title, and what its replies have cost so far. */
  title: string;
  cost: ReturnType<typeof describeCost>;
  onNewChat?: () => void;
  onOpenList: () => void;
}

/** The screen's name, the open chat, a way to start over once there is a conversation, and the (decorative) online status. */
function ChatHeader({ title, cost, onNewChat, onOpenList }: ChatHeaderProps) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-white/[0.06] bg-slate-950/30 px-4 py-4 sm:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenList}
          aria-label="Your chats"
          className={`${HEADER_BUTTON} px-2 md:hidden`}
        >
          <PanelLeft aria-hidden="true" className="size-4" />
        </button>
        <div className="min-w-0">
          <h1 className="text-xl font-extrabold tracking-tight">Chat</h1>
          <p className="truncate text-xs text-slate-400">
            {title}
            {cost && (
              <>
                {' · '}
                <CostText view={cost} compact />
              </>
            )}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-4">
        {onNewChat && (
          <button type="button" onClick={onNewChat} className={HEADER_BUTTON}>
            <SquarePen aria-hidden="true" className="size-4" />
            New chat
          </button>
        )}
        <div className="hidden items-center gap-2 text-sm text-slate-400 sm:flex">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full rounded-full bg-emerald-400 opacity-60 motion-safe:animate-ping" />
            <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
          </span>
          Online
        </div>
      </div>
    </header>
  );
}

export function ChatPage() {
  const chats = useChats();
  const { messages, isLoading, loadingChat, loadError, send } = useChatStream({
    chatId: chats.openId,
    ensureChat: chats.ensure,
    onReplyEnd: chats.refresh,
  });
  const [input, setInput] = useState('');
  // Below `md` the list is a drawer the header opens; choosing a chat closes it.
  const [listOpen, setListOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // A reply is drawn as soon as it has text or has used a tool; the typing dots
  // stand in until either lands.
  const visible = messages.filter((message) => message.text !== '' || message.tools.length > 0);
  const isFresh = messages.length === 1 && !loadingChat;
  const open = chats.chats.find((chat) => chat.id === chats.openId);
  const cost = describeCost(totalUsage(messages));

  // Keep the newest message in view as tokens stream in. The optional call
  // covers environments without scrollIntoView (jsdom, older embedded views).
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [messages, isLoading]);

  function handleSend() {
    if (isLoading || loadingChat || !input.trim()) return;
    void send(input);
    setInput('');
  }

  function pickSuggestion(prompt: string) {
    setInput(prompt);
    inputRef.current?.focus();
  }

  function newChat() {
    chats.startNew();
    setListOpen(false);
  }

  function selectChat(chatId: number) {
    chats.select(chatId);
    setListOpen(false);
  }

  const list = (
    <ChatList
      chats={chats.chats}
      openId={chats.openId}
      loading={chats.loading}
      error={chats.error}
      onNew={newChat}
      onSelect={selectChat}
      onRename={chats.rename}
      onDelete={chats.remove}
    />
  );

  return (
    <div className={`relative isolate flex overflow-hidden text-white ${FULL_SCREEN_HEIGHT}`}>
      <Aurora
        className="inset-x-0 top-0 -z-10 h-3/5 opacity-50"
        height={0.32}
        speed={0.6}
        mouseInteraction={false}
        dpr={0.75}
      />
      <aside className="hidden w-64 shrink-0 border-r border-white/[0.06] bg-slate-950/40 md:block">
        {list}
      </aside>
      {listOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            aria-hidden="true"
            onClick={() => setListOpen(false)}
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Your chats"
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-white/[0.08] bg-slate-950"
          >
            <div className="flex justify-end px-3 pt-3">
              <button
                type="button"
                onClick={() => setListOpen(false)}
                aria-label="Close the list"
                className={`rounded-lg p-2 text-slate-300 hover:bg-white/5 hover:text-slate-50 ${FOCUS_RING}`}
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            </div>
            <div className="min-h-0 flex-1">{list}</div>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <ChatHeader
          title={open ? open.title || UNTITLED_CHAT : UNTITLED_CHAT}
          cost={cost}
          onNewChat={isFresh ? undefined : newChat}
          onOpenList={() => setListOpen(true)}
        />

        <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
          <div className="mx-auto flex max-w-4xl flex-col gap-6">
            {loadError && (
              <p role="alert" className="text-sm text-rose-300">
                {loadError}
              </p>
            )}
            {loadingChat ? (
              <p className="text-sm text-slate-400">Opening the chat…</p>
            ) : (
              visible.map((message) => <MessageBubble key={message.id} message={message} />)
            )}
            {isLoading && <TypingIndicator />}
            {isFresh && <ChatSuggestions onPick={pickSuggestion} />}
            <div ref={endRef} />
          </div>
        </div>

        <ChatComposer
          ref={inputRef}
          value={input}
          disabled={isLoading || loadingChat}
          onChange={setInput}
          onSend={handleSend}
        />
      </div>
    </div>
  );
}
