import { useCallback, useEffect, useRef, useState } from 'react';

import { confirmDelivery, deleteDelivery, getDelivery } from '../../core/api/deliveries';
import type { Delivery } from '../../core/api/deliveryTypes';
import { errorMessage } from '../../core/api/errorMessage';

/**
 * One delivery, loaded when its card shows, and the person's two answers to it:
 * confirm (a first message is posted there) or cancel. Leaving cancels the load,
 * and an answer that comes back after it changes nothing.
 */
export function useDelivery(deliveryId: number) {
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [cancelled, setCancelled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    getDelivery(deliveryId, controller.signal)
      .then(setDelivery)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(errorMessage(cause, 'This delivery could not be loaded.'));
      });
    return () => {
      active.current = false;
      controller.abort();
    };
  }, [deliveryId]);

  const answer = useCallback(async (task: () => Promise<void>, failed: string) => {
    setBusy(true);
    setError('');
    try {
      await task();
    } catch (cause) {
      if (active.current) setError(errorMessage(cause, failed));
    } finally {
      if (active.current) setBusy(false);
    }
  }, []);

  const confirm = useCallback(
    () =>
      answer(async () => {
        const confirmed = await confirmDelivery(deliveryId);
        if (active.current) setDelivery(confirmed);
      }, 'The address could not be confirmed.'),
    [answer, deliveryId],
  );

  const cancel = useCallback(
    () =>
      answer(async () => {
        await deleteDelivery(deliveryId);
        if (active.current) setCancelled(true);
      }, 'The delivery could not be cancelled.'),
    [answer, deliveryId],
  );

  return { delivery, cancelled, busy, error, confirm, cancel };
}
