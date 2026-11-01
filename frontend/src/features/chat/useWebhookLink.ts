import { useEffect, useState } from 'react';

import { errorMessage } from '../../core/api/errorMessage';
import { getWebhook } from '../../core/api/webhooks';
import type { WebhookLink } from '../../core/api/webhookTypes';

/** One webhook with its secret link, loaded when its card shows; leaving cancels the request. */
export function useWebhookLink(webhookId: number) {
  const [link, setLink] = useState<WebhookLink | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getWebhook(webhookId, controller.signal)
      .then(setLink)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(errorMessage(cause, 'The webhook link could not be loaded.'));
      });
    return () => controller.abort();
  }, [webhookId]);

  return { link, error };
}
