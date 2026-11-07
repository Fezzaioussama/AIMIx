import { Link } from 'react-router-dom';

import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { DeliveryItem } from './DeliveryItem';
import { NoticeLine } from './NoticeLine';
import { useWebhooks } from './useWebhooks';
import type { HookLists } from './useWebhooks';
import { WebhookItem } from './WebhookItem';

interface ListProps {
  lists: NonNullable<HookLists>;
  busy: boolean;
  actions: ReturnType<typeof useWebhooks>['actions'];
}

function SectionIntro() {
  return (
    <>
      <h2 id="webhooks-heading" className="text-2xl font-bold tracking-tight">
        Webhooks
      </h2>
      <p className="mt-2 mb-6 text-sm text-slate-400">
        Links another app calls to start one of your workflows, and the Slack, Discord, email or
        other addresses a workflow&apos;s results are sent to when a run ends. You set them up by
        chatting; here you see them all, switch them off, get a new link or delete them.
      </p>
    </>
  );
}

/** What to ask the chat for when a list is still empty. */
function EmptyHint({ ask }: { ask: string }) {
  return (
    <p className="text-sm text-slate-400">
      None yet. In{' '}
      <Link to="/chat" className="text-sky-300 underline-offset-2 hover:underline">
        Chat
      </Link>
      , ask: &ldquo;{ask}&rdquo;
    </p>
  );
}

function WebhookList({ lists, busy, actions }: ListProps) {
  return (
    <section aria-labelledby="webhook-list-heading" className="space-y-4">
      <h3 id="webhook-list-heading" className="text-lg font-semibold">
        Start a workflow from another app
      </h3>
      {lists.webhooks.length === 0 && <EmptyHint ask="Let our form start my weekly digest." />}
      {lists.webhooks.map((webhook, index) => (
        <AnimatedContent key={webhook.id} distance={18} delay={index * 0.05}>
          <WebhookItem
            webhook={webhook}
            busy={busy}
            onToggle={(enabled) => void actions.setWebhookEnabled(webhook, enabled)}
            onRenew={() => actions.renewWebhook(webhook)}
            onDelete={() => void actions.removeWebhook(webhook)}
          />
        </AnimatedContent>
      ))}
    </section>
  );
}

function DeliveryList({ lists, busy, actions }: ListProps) {
  return (
    <section aria-labelledby="delivery-list-heading" className="space-y-4">
      <h3 id="delivery-list-heading" className="text-lg font-semibold">
        Send results to another app
      </h3>
      {lists.deliveries.length === 0 && (
        <EmptyHint ask="Send my weekly digest's results to our Slack." />
      )}
      {lists.deliveries.map((delivery, index) => (
        <AnimatedContent key={delivery.id} distance={18} delay={index * 0.05}>
          <DeliveryItem
            delivery={delivery}
            busy={busy}
            onToggle={(enabled) => void actions.setDeliveryEnabled(delivery, enabled)}
            onConfirm={() => void actions.confirmDelivery(delivery)}
            onDelete={() => void actions.removeDelivery(delivery)}
          />
        </AnimatedContent>
      ))}
    </section>
  );
}

/** Settings → Webhooks: what starts the account's workflows from other apps, and where
 *  their results go. Both are set up by chat; this is where a person sees and changes them. */
export function WebhooksSection() {
  const { lists, status, notice, actions } = useWebhooks();
  const busy = status !== 'idle';

  return (
    <section aria-labelledby="webhooks-heading" className="mt-8">
      <SectionIntro />
      {status === 'loading' && <p className="text-sm text-slate-400">Loading your webhooks…</p>}
      {lists && (
        <div className="space-y-10">
          <WebhookList lists={lists} busy={busy} actions={actions} />
          <DeliveryList lists={lists} busy={busy} actions={actions} />
        </div>
      )}
      {notice && (
        <div className="mt-4">
          <NoticeLine notice={notice} />
        </div>
      )}
    </section>
  );
}
