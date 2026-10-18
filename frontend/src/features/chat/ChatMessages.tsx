import { motion } from 'motion/react';

import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import type { ChatMessage } from './useChatStream';

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
});

const SPRING = { type: 'spring', stiffness: 380, damping: 30 } as const;

const USER_BUBBLE =
  'rounded-br-[0.3rem] bg-gradient-to-br from-sky-500 via-indigo-500 to-purple-600 text-white shadow-[0_8px_24px_-8px_rgba(99,102,241,0.6)]';
const AI_BUBBLE = 'rounded-bl-[0.3rem] border border-white/10 bg-slate-900/70 text-slate-100';

const SUGGESTIONS = [
  {
    title: 'Explain a concept',
    prompt: 'Explain how retrieval-augmented generation works, with a simple example.',
  },
  {
    title: 'Draft an email',
    prompt: 'Draft a short, friendly email announcing a product launch to our customers.',
  },
  { title: 'Summarise text', prompt: 'Summarise this text in five bullet points: ' },
  {
    title: 'Plan a pipeline',
    prompt: 'Suggest a multi-step AI pipeline that turns a blog post into social media posts.',
  },
] as const;

function AssistantAvatar() {
  return (
    <span
      aria-hidden="true"
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-sky-400 via-indigo-500 to-purple-500 text-[10px] font-bold text-white shadow-[0_0_18px_rgba(99,102,241,0.55)]"
    >
      AI
    </span>
  );
}

/** One message; it springs in once on mount and stays put while its text streams in. */
export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.sender === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={SPRING}
      className={`flex w-full items-end gap-3 ${isUser ? 'justify-end' : ''}`}
    >
      {!isUser && <AssistantAvatar />}
      <div
        className={`max-w-[85%] rounded-[1.2rem] px-5 py-4 text-base leading-relaxed sm:max-w-[75%] ${isUser ? USER_BUBBLE : AI_BUBBLE}`}
      >
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
    </motion.div>
  );
}

/** Stands in for the assistant's reply until its first token arrives. */
export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={SPRING}
      className="flex w-full items-end gap-3"
    >
      <AssistantAvatar />
      <div className="flex gap-1.5 rounded-[1.2rem] rounded-bl-[0.3rem] border border-white/10 bg-slate-900/70 px-6 py-4">
        <span className="animate-wave size-1.5 rounded-full bg-sky-400" />
        <span className="animate-wave size-1.5 rounded-full bg-indigo-400 [animation-delay:-1.1s]" />
        <span className="animate-wave size-1.5 rounded-full bg-purple-400 [animation-delay:-0.9s]" />
      </div>
    </motion.div>
  );
}

/** Prompt starters for an empty conversation; picking one fills the composer. */
export function ChatSuggestions({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 sm:pl-11">
      {SUGGESTIONS.map((suggestion, index) => (
        <AnimatedContent key={suggestion.title} distance={14} delay={0.3 + index * 0.08}>
          <button
            type="button"
            onClick={() => onPick(suggestion.prompt)}
            className="h-full w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-left transition duration-300 hover:-translate-y-0.5 hover:border-sky-400/40 hover:bg-sky-400/[0.06]"
          >
            <span className="block text-sm font-medium text-slate-100">{suggestion.title}</span>
            <span className="text-xs text-slate-400">{suggestion.prompt}</span>
          </button>
        </AnimatedContent>
      ))}
    </div>
  );
}
