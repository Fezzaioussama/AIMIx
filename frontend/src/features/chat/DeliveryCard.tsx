import { Send } from 'lucide-react';

import type { Delivery } from '../../core/api/deliveryTypes';
import { formatDateTime } from '../../core/time';
import { useDelivery } from './useDelivery';

const BUTTON =
  'rounded-md px-2.5 py-1 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50';

/** Where the results stand: waiting for the person, sending, or switched off. */
function DeliveryState({ delivery }: { delivery: Delivery }) {
  if (!delivery.confirmed)
    return (
      <p className="text-xs text-slate-300">
        Nothing is sent until you confirm. A first message is posted there to check it works.
      </p>
    );
  if (!delivery.enabled)
    return <p className="text-xs text-slate-400">Not sending: ask the chat to switch it on.</p>;
  return (
    <p className="text-xs text-emerald-300">
      Sending the results after every run
      {delivery.last_sent_at && ` · last sent ${formatDateTime(delivery.last_sent_at)}`}
      {delivery.last_error && <span className="text-rose-300"> · {delivery.last_error}</span>}
    </p>
  );
}

/**
 * Where a workflow's results go, as the chat proposed it: the address's host and last
 * characters, and the person's own Confirm or Cancel, so results never leave the
 * server on the model's word alone.
 */
export function DeliveryCard({ deliveryId }: { deliveryId: number }) {
  const { delivery, cancelled, busy, error, confirm, cancel } = useDelivery(deliveryId);

  if (cancelled) return <p className="mt-1.5 text-xs text-slate-400">Cancelled.</p>;
  if (!delivery)
    return (
      <p className={`mt-1.5 text-xs ${error ? 'text-rose-300' : 'text-slate-400'}`}>
        {error || 'Loading…'}
      </p>
    );
  return (
    <div className="mt-1.5 space-y-1.5 rounded-md bg-sky-400/10 px-2.5 py-2">
      <div className="flex items-center gap-2 text-sm font-medium text-sky-200">
        <Send aria-hidden="true" className="size-4 shrink-0" />
        <span className="truncate">
          Results of {delivery.pipeline_name} → {delivery.service}
        </span>
      </div>
      <p className="font-mono text-xs text-slate-300">
        {delivery.destination} …{delivery.hint}
      </p>
      <DeliveryState delivery={delivery} />
      {error && <p className="text-xs text-rose-300">{error}</p>}
      {!delivery.confirmed && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void confirm()}
            className={`${BUTTON} bg-sky-400 text-slate-950 enabled:hover:bg-sky-300`}
          >
            Confirm
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void cancel()}
            className={`${BUTTON} border border-white/10 text-slate-200 enabled:hover:border-white/20`}
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
