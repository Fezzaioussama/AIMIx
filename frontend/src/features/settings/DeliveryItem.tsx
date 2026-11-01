import { useRef, useState } from 'react';

import type { Delivery } from '../../core/api/deliveryTypes';
import { formatDateTime } from '../../core/time';
import { ToggleSwitch } from '../../core/ui/ToggleSwitch';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { actionButtonClass } from './actionButton';
import { ConfirmAction } from './ConfirmAction';

interface DeliveryItemProps {
  delivery: Delivery;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onConfirm: () => void;
  onDelete: () => void;
}

/** Whether results go there yet, and how the latest sending went, with its colour. */
function sendingState(delivery: Delivery): [string, string] {
  if (!delivery.confirmed)
    return [
      'Waiting for your OK: nothing is sent until you confirm. A first message is posted there to check it works.',
      'text-amber-200',
    ];
  if (!delivery.last_sent_at)
    return ['Nothing sent yet: results go there when a run ends.', 'text-slate-400'];
  const when = `Last sent ${formatDateTime(delivery.last_sent_at)}`;
  return delivery.last_error
    ? [`${when}: ${delivery.last_error}`, 'text-rose-300']
    : [`${when}.`, 'text-emerald-300'];
}

/** The workflow, where its results go (host and last characters only), and its switch. */
function DeliveryHeading({
  delivery,
  busy,
  onToggle,
}: Pick<DeliveryItemProps, 'delivery' | 'busy' | 'onToggle'>) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h4 id={`delivery-${delivery.id}`} className="truncate text-base font-semibold">
          {delivery.pipeline_name}
        </h4>
        <p className="truncate text-xs text-slate-400">
          Results to {delivery.service} ·{' '}
          <span className="font-mono">
            {delivery.destination} …{delivery.hint}
          </span>
        </p>
      </div>
      {delivery.confirmed && (
        <ToggleSwitch
          checked={delivery.enabled}
          label={`Send ${delivery.pipeline_name}'s results to ${delivery.service}`}
          disabled={busy}
          onChange={onToggle}
        />
      )}
    </div>
  );
}

/** Where one workflow's results are posted when a run ends: confirm, switch or remove it. */
export function DeliveryItem({ delivery, busy, onToggle, onConfirm, onDelete }: DeliveryItemProps) {
  const [asking, setAsking] = useState(false);
  const removeButton = useRef<HTMLButtonElement>(null);
  const name = delivery.pipeline_name;
  const [state, tone] = sendingState(delivery);

  return (
    <SpotlightCard as="section" aria-labelledby={`delivery-${delivery.id}`} className="p-5">
      <DeliveryHeading delivery={delivery} busy={busy} onToggle={onToggle} />
      <p className={`mt-2 text-xs ${tone}`}>{state}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {!delivery.confirmed && (
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={actionButtonClass('accent')}
          >
            Confirm
          </button>
        )}
        <button
          ref={removeButton}
          type="button"
          onClick={() => setAsking(true)}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Remove
        </button>
      </div>
      {asking && (
        <ConfirmAction
          question={`Stop sending ${name}'s results to ${delivery.service}?`}
          consequence="The address is removed. The chat can set one again any time."
          confirmLabel="Remove the address"
          keepLabel="Keep it"
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => {
            setAsking(false);
            removeButton.current?.focus();
          }}
        />
      )}
    </SpotlightCard>
  );
}
