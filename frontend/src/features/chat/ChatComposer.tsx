import type { Ref } from 'react';

import { ClickSpark } from '../../core/ui/reactbits/ClickSpark';

interface ChatComposerProps {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  ref?: Ref<HTMLInputElement>;
}

/** The message box: Enter or the send button submits; `ref` lets starter prompts focus it. */
export function ChatComposer({ value, disabled, onChange, onSend, ref }: ChatComposerProps) {
  return (
    <div className="p-4 sm:p-6">
      <div className="mx-auto flex max-w-4xl gap-3 rounded-2xl border border-white/10 bg-slate-900/70 p-2 shadow-[0_20px_50px_-20px_rgba(0,0,0,0.8)] backdrop-blur-xl transition-[border-color,box-shadow] duration-300 focus-within:border-sky-400/40 focus-within:shadow-[0_0_0_4px_rgba(56,189,248,0.08),0_20px_50px_-20px_rgba(0,0,0,0.8)]">
        <input
          ref={ref}
          type="text"
          value={value}
          disabled={disabled}
          placeholder="Ask anything…"
          onChange={(event) => onChange(event.target.value)}
          onKeyUp={(event) => event.key === 'Enter' && onSend()}
          className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base text-white outline-none placeholder:text-slate-500"
        />
        <ClickSpark className="inline-flex">
          <button
            type="button"
            onClick={onSend}
            disabled={disabled || !value.trim()}
            aria-label="Send message"
            className="flex size-11 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 via-indigo-500 to-purple-500 text-white transition duration-300 enabled:hover:scale-105 enabled:hover:shadow-[0_0_24px_rgba(99,102,241,0.6)] enabled:active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="size-5"
            >
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
            </svg>
          </button>
        </ClickSpark>
      </div>
    </div>
  );
}
