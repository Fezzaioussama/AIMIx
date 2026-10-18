import { useEffect, useRef, useState } from 'react';

import { BrandMark } from '../../core/ui/BrandMark';
import { Aurora } from '../../core/ui/reactbits/Aurora';
import { ShinyText } from '../../core/ui/reactbits/ShinyText';
import { ChatComposer } from './ChatComposer';
import { ChatSuggestions, MessageBubble, TypingIndicator } from './ChatMessages';
import { useChatStream } from './useChatStream';

/** Wordmark and the (decorative) online status above the transcript. */
function ChatHeader() {
  return (
    <header className="flex items-center justify-between border-b border-white/[0.06] bg-slate-950/30 px-4 py-4 sm:px-8">
      <div className="flex items-baseline gap-3">
        <BrandMark />
        <ShinyText className="text-sm text-slate-400/70">Assistant</ShinyText>
      </div>
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <span className="relative flex size-2">
          <span className="absolute inline-flex size-full rounded-full bg-emerald-400 opacity-60 motion-safe:animate-ping" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
        </span>
        Online
      </div>
    </header>
  );
}

export function ChatPage() {
  const { messages, isLoading, send } = useChatStream();
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // A reply is drawn once its first token lands; until then the typing dots stand in.
  const visible = messages.filter((message) => message.text !== '');
  const isFresh = messages.length === 1;

  // Keep the newest message in view as tokens stream in. The optional call
  // covers environments without scrollIntoView (jsdom, older embedded views).
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  }, [messages, isLoading]);

  function handleSend() {
    if (isLoading || !input.trim()) return;
    void send(input);
    setInput('');
  }

  function pickSuggestion(prompt: string) {
    setInput(prompt);
    inputRef.current?.focus();
  }

  return (
    <div className="relative isolate flex h-[calc(100vh-60px)] flex-col overflow-hidden text-white">
      <Aurora
        className="inset-x-0 top-0 -z-10 h-3/5 opacity-50"
        height={0.32}
        speed={0.6}
        mouseInteraction={false}
        dpr={0.75}
      />
      <ChatHeader />

      <div className="flex-1 overflow-y-auto px-4 py-8 sm:px-8">
        <div className="mx-auto flex max-w-4xl flex-col gap-6">
          {visible.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isLoading && <TypingIndicator />}
          {isFresh && <ChatSuggestions onPick={pickSuggestion} />}
          <div ref={endRef} />
        </div>
      </div>

      <ChatComposer
        ref={inputRef}
        value={input}
        disabled={isLoading}
        onChange={setInput}
        onSend={handleSend}
      />
    </div>
  );
}
