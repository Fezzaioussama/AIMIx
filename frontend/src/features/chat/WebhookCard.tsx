import { Check, Copy, Webhook } from 'lucide-react';

import { webhookUrl } from '../../core/api/webhooks';
import { useCopyToClipboard } from '../../core/hooks/useCopyToClipboard';
import { useWebhookLink } from './useWebhookLink';

/**
 * A webhook's secret link, read from the server for its owner (the chat's model never sees
 * it), with a copy button and one line on how another app uses it.
 */
export function WebhookCard({ webhookId }: { webhookId: number }) {
  const { link, error } = useWebhookLink(webhookId);
  const { status, copy } = useCopyToClipboard();
  const copied = status === 'copied';

  if (error) return <p className="mt-1.5 text-xs text-rose-300">{error}</p>;
  if (!link) return <p className="mt-1.5 text-xs text-slate-400">Loading the link…</p>;
  const url = webhookUrl(link.token);
  return (
    <div className="mt-1.5 rounded-md bg-sky-400/10 px-2.5 py-2">
      <div className="flex items-center gap-2 text-sm font-medium text-sky-200">
        <Webhook aria-hidden="true" className="size-4 shrink-0" />
        <span className="truncate">{link.pipeline_name}</span>
        <span className="ml-auto shrink-0 text-xs text-sky-300/70">
          {link.enabled ? 'On' : 'Off'}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <code
          title={url}
          className="min-w-0 flex-1 truncate rounded bg-slate-950/60 px-2 py-1 font-mono text-xs text-slate-200"
        >
          {url}
        </code>
        <button
          type="button"
          onClick={() => void copy(url)}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-slate-200 transition hover:border-white/20 hover:text-white"
        >
          {copied ? (
            <Check aria-hidden="true" className="size-3.5" />
          ) : (
            <Copy aria-hidden="true" className="size-3.5" />
          )}
          {copied ? 'Copied' : 'Copy link'}
        </button>
      </div>
      <p className="mt-1.5 text-xs text-slate-400">
        Another app starts this workflow by sending a POST with JSON or text to this link. Keep it
        private: anyone who has it can start a run.
      </p>
    </div>
  );
}
