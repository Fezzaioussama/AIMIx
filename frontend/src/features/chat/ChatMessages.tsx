import { motion } from 'motion/react';
import { Link } from 'react-router-dom';

import type { ChatAction } from '../../core/api/chatTypes';
import { missionPath } from '../../core/routes';
import { renderMarkdown } from '../../core/markdown/renderMarkdown';
import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SCHEDULES_PATH } from '../schedules/paths';
import type { ChatMessage, ChatToolRun } from './useChatStream';

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
    title: 'Build a workflow',
    prompt:
      "Every Monday, find the week's news about my competitors and write me a one-page summary.",
  },
  {
    title: 'What can my agents use?',
    prompt: 'Which tools can my agents use?',
  },
  {
    title: 'What can I run?',
    prompt: 'List my workflows and tell me what each one does.',
  },
  {
    title: 'Schedule a run',
    prompt: 'Run my newest workflow every weekday at 9:00.',
  },
] as const;

/** Where a finished tool's result opens in the app. */
function actionPath(action: ChatAction): string {
  return action.kind === 'schedule' ? SCHEDULES_PATH : missionPath(action.id);
}

const STATUS_DOT = {
  started: 'bg-sky-400 animate-pulse',
  finished: 'bg-emerald-400',
  failed: 'bg-rose-400',
} as const;

/** One tool the reply used: what it did, and a link to what it made. */
function ToolActivity({ run }: { run: ChatToolRun }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2">
      <div className="flex items-center gap-2 text-xs">
        <span
          aria-hidden="true"
          className={`size-1.5 shrink-0 rounded-full ${STATUS_DOT[run.status]}`}
        />
        <span className={run.status === 'failed' ? 'text-rose-300' : 'text-slate-300'}>
          {run.label}
        </span>
        {run.detail && <span className="text-slate-500">· {run.detail}</span>}
      </div>
      {run.action && (
        <Link
          to={actionPath(run.action)}
          className="mt-1.5 flex items-center justify-between gap-3 rounded-md bg-sky-400/10 px-2.5 py-1.5 transition hover:bg-sky-400/20"
        >
          <span className="truncate text-sm font-medium text-sky-200">{run.action.title}</span>
          <span className="shrink-0 text-xs text-sky-300/70">{run.action.subtitle} →</span>
        </Link>
      )}
    </div>
  );
}

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
          <>
            {message.tools.length > 0 && (
              <div className="mb-2 flex flex-col gap-1.5">
                {message.tools.map((run) => (
                  <ToolActivity key={run.id} run={run} />
                ))}
              </div>
            )}
            {message.text && (
              <div
                className="prose-output"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(message.text) }}
              />
            )}
          </>
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
