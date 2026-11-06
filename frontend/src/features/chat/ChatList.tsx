import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';

import type { ChatSummary } from '../../core/api/chatTypes';
import { formatDateTime } from '../../core/time';
import { FOCUS_RING } from '../../core/ui/focus';
import { actionButtonClass } from '../settings/actionButton';

/** What an unnamed chat is called until something is said in it. */
export const UNTITLED_CHAT = 'New chat';

const ICON_BUTTON = `rounded-md p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-slate-100 ${FOCUS_RING}`;

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={ICON_BUTTON}
    >
      {children}
    </button>
  );
}

interface RenameFormProps {
  title: string;
  /** True once the chat is renamed, which closes the field; false keeps it open to retry. */
  onSave: (title: string) => Promise<boolean>;
  onCancel: () => void;
}

/** Renaming in place: Enter (or leaving the field) saves, Escape leaves the title as it was. */
function RenameForm({ title, onSave, onCancel }: RenameFormProps) {
  const [value, setValue] = useState(title);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const next = value.trim();
    if (!next || next === title) {
      onCancel();
      return;
    }
    setSaving(true);
    if (!(await onSave(next))) setSaving(false);
  }
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') onCancel();
  }
  return (
    <form onSubmit={submit} className="px-2 py-1.5">
      <input
        autoFocus
        aria-label="Chat title"
        value={value}
        maxLength={100}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={(event) => void submit(event)}
        disabled={saving}
        className={`w-full rounded-md border border-white/10 bg-slate-900/70 px-2 py-1 text-sm text-slate-100 ${FOCUS_RING}`}
      />
    </form>
  );
}

interface ChatItemProps {
  chat: ChatSummary;
  open: boolean;
  onSelect: (chatId: number) => void;
  onRename: (chatId: number, title: string) => Promise<boolean>;
  onDelete: (chatId: number) => Promise<boolean>;
}

/** One chat: its title and when it was last written to; rename or delete it in place. */
function ChatItem({ chat, open, onSelect, onRename, onDelete }: ChatItemProps) {
  const [mode, setMode] = useState<'view' | 'rename' | 'delete'>('view');
  const [busy, setBusy] = useState(false);
  const title = chat.title || UNTITLED_CHAT;

  async function rename(next: string) {
    const renamed = await onRename(chat.id, next);
    if (renamed) setMode('view');
    return renamed;
  }

  async function remove() {
    setBusy(true);
    if (!(await onDelete(chat.id))) setBusy(false);
  }

  if (mode === 'rename') {
    return <RenameForm title={chat.title} onSave={rename} onCancel={() => setMode('view')} />;
  }
  return (
    <div className={`group rounded-lg ${open ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]'}`}>
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => onSelect(chat.id)}
          aria-current={open ? 'true' : undefined}
          className={`min-w-0 flex-1 rounded-lg px-3 py-2 text-left ${FOCUS_RING}`}
        >
          <span className="block truncate text-sm text-slate-100">{title}</span>
          <span className="block text-[0.7rem] text-slate-500">
            {formatDateTime(chat.updated_at)}
          </span>
        </button>
        <span className="flex shrink-0 gap-0.5 pr-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100 pointer-coarse:opacity-100">
          <IconButton label={`Rename ${title}`} onClick={() => setMode('rename')}>
            <Pencil aria-hidden="true" className="size-3.5" />
          </IconButton>
          <IconButton label={`Delete ${title}`} onClick={() => setMode('delete')}>
            <Trash2 aria-hidden="true" className="size-3.5" />
          </IconButton>
        </span>
      </div>
      {mode === 'delete' && (
        <div
          role="group"
          aria-label={`Delete ${title}?`}
          className="px-3 pb-2 text-xs text-slate-300"
        >
          Delete this chat? Everything said in it goes with it.
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => void remove()}
              disabled={busy}
              className={actionButtonClass('danger')}
            >
              Delete
            </button>
            <button
              type="button"
              autoFocus
              onClick={() => setMode('view')}
              className={actionButtonClass()}
            >
              Keep it
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface ChatListProps {
  chats: ChatSummary[];
  openId: number | null;
  loading: boolean;
  error: string;
  onNew: () => void;
  onSelect: (chatId: number) => void;
  onRename: (chatId: number, title: string) => Promise<boolean>;
  onDelete: (chatId: number) => Promise<boolean>;
}

/** The person's chats, the one last written to first, and a way to start a new one. */
export function ChatList({
  chats,
  openId,
  loading,
  error,
  onNew,
  onSelect,
  onRename,
  onDelete,
}: ChatListProps) {
  return (
    <nav aria-label="Your chats" className="flex h-full flex-col">
      <div className="px-3 pt-4 pb-2">
        <button
          type="button"
          onClick={onNew}
          className={`inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 transition hover:border-white/20 hover:text-white ${FOCUS_RING}`}
        >
          <Plus aria-hidden="true" className="size-4" />
          New chat
        </button>
      </div>
      {error && (
        <p role="alert" className="px-3 pb-2 text-xs text-rose-300">
          {error}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading ? (
          <p className="px-2 text-xs text-slate-500">Loading your chats…</p>
        ) : chats.length === 0 ? (
          <p className="px-2 text-xs text-slate-500">Your chats will be listed here.</p>
        ) : (
          <ul className="space-y-0.5">
            {chats.map((chat) => (
              <li key={chat.id}>
                <ChatItem
                  chat={chat}
                  open={chat.id === openId}
                  onSelect={onSelect}
                  onRename={onRename}
                  onDelete={onDelete}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
