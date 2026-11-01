import { useRef, useState } from 'react';

import type { Webhook } from '../../core/api/webhookTypes';
import { formatDateTime } from '../../core/time';
import { ToggleSwitch } from '../../core/ui/ToggleSwitch';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { WebhookCard } from '../chat/WebhookCard';
import { actionButtonClass } from './actionButton';
import { ConfirmAction } from './ConfirmAction';
import type { ConfirmCopy } from './ConfirmAction';

interface WebhookItemProps {
  webhook: Webhook;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  /** Resolves true once the new link is saved. */
  onRenew: () => Promise<boolean>;
  onDelete: () => void;
}

type Asking = 'renew' | 'delete';

/** What each action asks before it acts, by the workflow's name. */
const QUESTIONS: Record<Asking, (name: string) => ConfirmCopy> = {
  renew: (name) => ({
    question: `Give ${name} a new link?`,
    consequence:
      'The current link stops working at once: give the new one to the apps that call it.',
    confirmLabel: 'Get a new link',
    keepLabel: 'Keep this link',
  }),
  delete: (name) => ({
    question: `Delete ${name}'s link?`,
    consequence:
      'Apps that call it can no longer start this workflow. The chat can make a new link any time.',
    confirmLabel: 'Delete the link',
    keepLabel: 'Keep it',
  }),
};

/** When its link was last called, and whether that started a run. */
function lastCall(webhook: Webhook): string {
  if (!webhook.last_called_at) return 'Not called yet.';
  const when = `Last called ${formatDateTime(webhook.last_called_at)}`;
  return webhook.last_error ? `${when}: ${webhook.last_error}` : `${when}: a run started.`;
}

function WebhookHeading({
  webhook,
  busy,
  onToggle,
}: Omit<WebhookItemProps, 'onRenew' | 'onDelete'>) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h4 id={`webhook-${webhook.id}`} className="truncate text-base font-semibold">
          {webhook.pipeline_name}
        </h4>
        <p className={`mt-0.5 text-xs ${webhook.last_error ? 'text-rose-300' : 'text-slate-400'}`}>
          {lastCall(webhook)}
        </p>
      </div>
      <ToggleSwitch
        checked={webhook.enabled}
        label={`Let other apps start ${webhook.pipeline_name}`}
        disabled={busy}
        onChange={onToggle}
      />
    </div>
  );
}

/** A link another app calls to start one workflow: switch it, show it, renew it or delete it. */
export function WebhookItem({ webhook, busy, onToggle, onRenew, onDelete }: WebhookItemProps) {
  const [asking, setAsking] = useState<Asking | null>(null);
  const [showing, setShowing] = useState(false);
  // A renewed link is read again from the server when it shows.
  const [version, setVersion] = useState(0);
  const buttons = {
    renew: useRef<HTMLButtonElement>(null),
    delete: useRef<HTMLButtonElement>(null),
  };

  const act = async () => {
    if (asking === 'renew' && (await onRenew())) setVersion((current) => current + 1);
    if (asking === 'delete') onDelete();
    setAsking(null);
  };
  const keep = () => {
    if (asking) buttons[asking].current?.focus();
    setAsking(null);
  };
  const ask = (action: Asking, label: string, tone: 'neutral' | 'danger') => (
    <button
      ref={buttons[action]}
      type="button"
      onClick={() => setAsking(action)}
      disabled={busy}
      className={actionButtonClass(tone)}
    >
      {label}
    </button>
  );

  return (
    <SpotlightCard as="section" aria-labelledby={`webhook-${webhook.id}`} className="p-5">
      <WebhookHeading webhook={webhook} busy={busy} onToggle={onToggle} />
      {showing && <WebhookCard key={version} webhookId={webhook.id} />}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setShowing((current) => !current)}
          aria-expanded={showing}
          className={actionButtonClass('accent')}
        >
          {showing ? 'Hide link' : 'Show link'}
        </button>
        {ask('renew', 'New link', 'neutral')}
        {ask('delete', 'Delete', 'danger')}
      </div>
      {asking && (
        <ConfirmAction
          {...QUESTIONS[asking](webhook.pipeline_name)}
          busy={busy}
          onConfirm={() => void act()}
          onCancel={keep}
        />
      )}
    </SpotlightCard>
  );
}
