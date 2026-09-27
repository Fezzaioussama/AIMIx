import { useEffect, useRef, useState } from 'react';

import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import { useChatStream } from './useChatStream';
import type { ChatMessage } from './useChatStream';

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
});

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.sender === 'user';
  const bubbleClass = isUser
    ? 'rounded-br-[0.2rem] bg-gradient-to-br from-[#667eea] to-[#764ba2] text-white shadow-[0_4px_15px_rgba(102,126,234,0.3)]'
    : 'rounded-bl-[0.2rem] border border-white/10 bg-white/8 text-[#e0e0e0] backdrop-blur-sm';

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : ''}`}>
      <div className={`max-w-[70%] rounded-[1.2rem] px-5 py-4 text-base leading-relaxed ${bubbleClass}`}>
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.text}</div>
        ) : (
          <div
            className="prose-output"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(message.text) }}
          />
        )}
        <span className="mt-2 block text-[0.7rem] opacity-60">
          {timeFormatter.format(message.timestamp)}
        </span>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex w-full">
      <div className="flex gap-1 rounded-[1.2rem] border border-white/10 bg-white/8 px-6 py-4">
        <span className="animate-wave size-1.5 rounded-full bg-[#aaa]" />
        <span className="animate-wave size-1.5 rounded-full bg-[#aaa] [animation-delay:-1.1s]" />
        <span className="animate-wave size-1.5 rounded-full bg-[#aaa] [animation-delay:-0.9s]" />
      </div>
    </div>
  );
}

export function ChatPage() {
  const { messages, isLoading, send } = useChatStream();
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

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

  return (
    <div className="flex h-[calc(100vh-60px)] flex-col bg-[radial-gradient(circle_at_top_left,#1a1a2e,#16213e)] text-white">
      <header className="flex items-center justify-between border-b border-white/10 bg-white/5 px-8 py-6 backdrop-blur-md">
        <div className="text-2xl font-extrabold">
          <span className="bg-gradient-to-r from-[#00d2ff] to-[#3a7bd5] bg-clip-text text-transparent">
            AI
          </span>
          Mix
        </div>
        <div className="flex items-center gap-2 text-sm text-[#a0a0a0]">
          <span className="size-2 rounded-full bg-[#00ff88] shadow-[0_0_10px_#00ff88]" />
          Online
        </div>
      </header>

      <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-8">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {isLoading && <TypingIndicator />}
        <div ref={endRef} />
      </div>

      <div className="bg-black/20 p-8">
        <div className="mx-auto flex max-w-[900px] gap-4 rounded-2xl border border-white/10 bg-white/5 p-2 backdrop-blur-md">
          <input
            type="text"
            value={input}
            disabled={isLoading}
            placeholder="Type your message..."
            onChange={(event) => setInput(event.target.value)}
            onKeyUp={(event) => event.key === 'Enter' && handleSend()}
            className="flex-1 bg-transparent px-4 py-3 text-base text-white outline-none placeholder:text-slate-400"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            aria-label="Send message"
            className="flex size-11 items-center justify-center rounded-[0.8rem] bg-gradient-to-r from-[#00d2ff] to-[#3a7bd5] text-white transition-transform hover:-translate-y-0.5 hover:shadow-[0_4px_15px_rgba(0,210,255,0.4)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-5">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
