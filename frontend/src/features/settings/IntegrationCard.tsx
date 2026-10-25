import { useRef, useState } from 'react';

import type { Integration } from '../../core/api/types';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { actionButtonClass } from './actionButton';
import { ConnectionTestResult, toolCount } from './ConnectionTestResult';
import { hostOf } from './integrationDraft';
import { SwitchButton } from './SwitchButton';
import type { ConnectionTest } from './useIntegrations';

interface IntegrationCardProps {
  integration: Integration;
  test?: ConnectionTest;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onToggleApproval: (required: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
}

function EnabledSwitch({
  integration,
  busy,
  onToggle,
}: Pick<IntegrationCardProps, 'integration' | 'busy' | 'onToggle'>) {
  const { enabled, name } = integration;
  return (
    <div className="flex shrink-0 items-center gap-2">
      <span aria-hidden="true" className="text-xs text-slate-300">
        {enabled ? 'On' : 'Off'}
      </span>
      <SwitchButton
        checked={enabled}
        disabled={busy}
        onChange={onToggle}
        label={`Let agents use ${name}`}
      />
    </div>
  );
}

/** Whether a run stops for the owner's OK before this integration's tools act. */
function ApprovalSwitch({
  integration,
  busy,
  onToggleApproval,
}: Pick<IntegrationCardProps, 'integration' | 'busy' | 'onToggleApproval'>) {
  const labelId = `integration-${integration.id}-approval`;
  const hintId = `${labelId}-hint`;
  const asks = integration.require_approval;
  return (
    <div className="mt-3 flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2.5">
      <div className="min-w-0">
        <p id={labelId} className="text-sm text-slate-100">
          Ask me before its tools act
        </p>
        <p id={hintId} className="mt-0.5 text-xs text-slate-400">
          {asks
            ? 'In a run, each action waits for your OK first.'
            : 'Its tools act without asking you first.'}
        </p>
      </div>
      <SwitchButton
        checked={asks}
        disabled={busy}
        onChange={onToggleApproval}
        labelledBy={labelId}
        describedBy={hintId}
      />
    </div>
  );
}

function headerSummary(integration: Integration): string {
  const count = integration.headers.length;
  if (count === 0) return 'No headers';
  return count === 1 ? `1 header: ${integration.headers[0].name}` : `${count} headers`;
}

interface DeleteConfirmProps {
  name: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function DeleteConfirm({ name, busy, onConfirm, onCancel }: DeleteConfirmProps) {
  return (
    <div
      role="group"
      aria-label={`Delete ${name}?`}
      className="mt-4 rounded-lg border border-red-400/30 bg-red-500/5 p-3 text-sm"
    >
      <p className="text-slate-200">
        Delete {name}? Steps that use its tools stop working until you connect it again.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Delete {name}
        </button>
        <button type="button" onClick={onCancel} autoFocus className={actionButtonClass()}>
          Keep it
        </button>
      </div>
    </div>
  );
}

type CardHeadingProps = Pick<IntegrationCardProps, 'integration' | 'test' | 'busy' | 'onToggle'> & {
  headingId: string;
};

/** Name, host, the on/off switch, and what is known about it so far. */
function CardHeading({ headingId, integration, test, busy, onToggle }: CardHeadingProps) {
  const tools = test?.status === 'passed' ? toolCount(test.tools.length) : null;
  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id={headingId} className="truncate font-mono text-lg font-semibold">
            {integration.name}
          </h3>
          <p className="truncate text-xs text-slate-400">{hostOf(integration.url)}</p>
        </div>
        <EnabledSwitch integration={integration} busy={busy} onToggle={onToggle} />
      </div>
      <p className="mt-2 text-xs text-slate-400">
        {headerSummary(integration)}
        {tools && <span className="text-sky-300"> · {tools} found</span>}
        {!integration.enabled && ' · Off: agents do not use it'}
      </p>
    </>
  );
}

/** One of the account's MCP servers: what it is, whether agents use it, and its actions. */
export function IntegrationCard({
  integration,
  test,
  busy,
  onToggle,
  onToggleApproval,
  onEdit,
  onDelete,
  onTest,
}: IntegrationCardProps) {
  const [confirming, setConfirming] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);
  const headingId = `integration-${integration.id}`;

  return (
    <SpotlightCard as="section" aria-labelledby={headingId} className="p-5">
      <CardHeading
        headingId={headingId}
        integration={integration}
        test={test}
        busy={busy}
        onToggle={onToggle}
      />
      <ApprovalSwitch integration={integration} busy={busy} onToggleApproval={onToggleApproval} />
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onTest}
          disabled={test?.status === 'testing'}
          className={actionButtonClass('accent')}
        >
          Test connection
        </button>
        <button type="button" onClick={onEdit} disabled={busy} className={actionButtonClass()}>
          Edit
        </button>
        <button
          ref={deleteButton}
          type="button"
          onClick={() => setConfirming(true)}
          disabled={busy}
          className={actionButtonClass('danger')}
        >
          Delete
        </button>
      </div>
      {confirming && (
        <DeleteConfirm
          name={integration.name}
          busy={busy}
          onConfirm={onDelete}
          onCancel={() => {
            setConfirming(false);
            deleteButton.current?.focus();
          }}
        />
      )}
      <ConnectionTestResult name={integration.name} test={test} />
    </SpotlightCard>
  );
}
