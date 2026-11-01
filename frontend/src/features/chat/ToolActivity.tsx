import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { ChatAction, ChatActionKind } from '../../core/api/chatTypes';
import { missionPath, runPath } from '../../core/routes';
import { SCHEDULES_PATH } from '../schedules/paths';
import type { ChatToolRun } from './useChatStream';
import { WebhookCard } from './WebhookCard';

const STATUS_DOT = {
  started: 'bg-sky-400 animate-pulse',
  finished: 'bg-emerald-400',
  failed: 'bg-rose-400',
} as const;

/** Where a finished tool's result opens in the app. */
function ActionLink({ action, to }: { action: ChatAction; to: string }) {
  return (
    <Link
      to={to}
      className="mt-1.5 flex items-center justify-between gap-3 rounded-md bg-sky-400/10 px-2.5 py-1.5 transition hover:bg-sky-400/20"
    >
      <span className="truncate text-sm font-medium text-sky-200">{action.title}</span>
      <span className="shrink-0 text-xs text-sky-300/70">{action.subtitle} →</span>
    </Link>
  );
}

/** How what a tool made is shown under it, by what it is (§5 O: a new kind is one entry). */
const ACTION_VIEWS: Record<ChatActionKind, (action: ChatAction) => ReactNode> = {
  pipeline: (action) => <ActionLink action={action} to={missionPath(action.id)} />,
  schedule: (action) => <ActionLink action={action} to={SCHEDULES_PATH} />,
  run: (action) => <ActionLink action={action} to={runPath(action.id)} />,
  webhook: (action) => <WebhookCard webhookId={action.id} />,
};

/** One tool the reply used: what it did, and what it made. */
export function ToolActivity({ run }: { run: ChatToolRun }) {
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
      {run.action && ACTION_VIEWS[run.action.kind](run.action)}
    </div>
  );
}
