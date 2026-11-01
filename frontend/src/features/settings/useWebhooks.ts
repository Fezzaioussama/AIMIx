import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

import * as deliveriesApi from '../../core/api/deliveries';
import type { Delivery } from '../../core/api/deliveryTypes';
import * as webhooksApi from '../../core/api/webhooks';
import type { Webhook } from '../../core/api/webhookTypes';
import { errorText, useSubmission } from './useSubmission';
import type { Submission } from './useSubmission';

/** The account's webhooks and result deliveries, or null until both are loaded. */
export type HookLists = { webhooks: Webhook[]; deliveries: Delivery[] } | null;

type SetLists = Dispatch<SetStateAction<HookLists>>;

/** Both lists, loaded together once; a failure goes to the section's notice. */
function useHookLists({ setNotice, setStatus }: Submission) {
  const [lists, setLists] = useState<HookLists>(null);

  useEffect(() => {
    let active = true;
    Promise.all([webhooksApi.listWebhooks(), deliveriesApi.listDeliveries()])
      .then(([webhooks, deliveries]) => {
        if (active) setLists({ webhooks, deliveries });
      })
      .catch((cause: unknown) => {
        if (active)
          setNotice({ kind: 'error', text: errorText(cause, 'Could not load your webhooks.') });
      })
      .finally(() => {
        if (active) setStatus('idle');
      });
    return () => {
      active = false;
    };
  }, [setNotice, setStatus]);

  return [lists, setLists] as const;
}

function replaced<T extends { id: number }>(items: T[], saved: T): T[] {
  return items.map((item) => (item.id === saved.id ? saved : item));
}

/** Switch a webhook, give it a new link, or delete it; each says how it went. */
function webhookActions(submit: Submission['submit'], setLists: SetLists) {
  const put = (saved: Webhook) =>
    setLists((current) => current && { ...current, webhooks: replaced(current.webhooks, saved) });
  return {
    setWebhookEnabled: (webhook: Webhook, enabled: boolean) =>
      submit(
        async () => put(await webhooksApi.setWebhookEnabled(webhook.id, enabled)),
        enabled
          ? `Other apps can start ${webhook.pipeline_name} again.`
          : `${webhook.pipeline_name}'s link is off: calling it starts nothing.`,
        'Could not change the webhook.',
      ),
    renewWebhook: (webhook: Webhook) =>
      submit(
        async () => put(await webhooksApi.renewWebhook(webhook.id)),
        `${webhook.pipeline_name} has a new link: give it to the apps that call it.`,
        'Could not renew the link.',
      ),
    removeWebhook: (webhook: Webhook) =>
      submit(
        async () => {
          await webhooksApi.deleteWebhook(webhook.id);
          setLists(
            (current) =>
              current && {
                ...current,
                webhooks: current.webhooks.filter((item) => item.id !== webhook.id),
              },
          );
        },
        `${webhook.pipeline_name}'s link is deleted.`,
        'Could not delete the webhook.',
      ),
  };
}

/** Confirm, switch or remove where a workflow's results go; each says how it went. */
function deliveryActions(submit: Submission['submit'], setLists: SetLists) {
  const put = (saved: Delivery) =>
    setLists(
      (current) => current && { ...current, deliveries: replaced(current.deliveries, saved) },
    );
  return {
    confirmDelivery: (delivery: Delivery) =>
      submit(
        async () => put(await deliveriesApi.confirmDelivery(delivery.id)),
        `${delivery.pipeline_name}'s results now go to ${delivery.service}.`,
        'Could not confirm the address.',
      ),
    setDeliveryEnabled: (delivery: Delivery, enabled: boolean) =>
      submit(
        async () => put(await deliveriesApi.setDeliveryEnabled(delivery.id, enabled)),
        enabled
          ? `${delivery.pipeline_name}'s results go to ${delivery.service} again.`
          : `${delivery.pipeline_name}'s results are no longer sent to ${delivery.service}.`,
        'Could not change where the results go.',
      ),
    removeDelivery: (delivery: Delivery) =>
      submit(
        async () => {
          await deliveriesApi.deleteDelivery(delivery.id);
          setLists(
            (current) =>
              current && {
                ...current,
                deliveries: current.deliveries.filter((item) => item.id !== delivery.id),
              },
          );
        },
        `${delivery.pipeline_name}'s results are no longer sent anywhere.`,
        'Could not remove the address.',
      ),
  };
}

/** State and transport for Settings → Webhooks, kept out of the components (§2). */
export function useWebhooks() {
  const submission = useSubmission('loading');
  const { status, notice, submit } = submission;
  const [lists, setLists] = useHookLists(submission);

  return {
    lists,
    status,
    notice,
    actions: { ...webhookActions(submit, setLists), ...deliveryActions(submit, setLists) },
  };
}
